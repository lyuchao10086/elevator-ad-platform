#include "Watchdog.hpp"
#include "Log.hpp"
#include <iostream>
#include <fstream>
#include <thread>
#include <chrono>
#include <random>
#include <iomanip>
#include <sstream>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>
#include <signal.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <fcntl.h>

Watchdog::Watchdog(const std::string& configPath, const std::string& exePath) 
    : configPath_(configPath), exePath_(exePath) {
    if (!loadConfig()) {
        std::cerr << "[Watchdog] 加载配置失败" << std::endl;
        return;
    }
    db_ = std::make_unique<Database>(config_.db_path);
    network_ = std::make_unique<NetworkClient>(config_.gateway_ws_url, config_.device_id, config_.token);
}

Watchdog::~Watchdog() {
    stopPlayer();
    if (network_) {
        network_->stopGatewayConnection();
    }
}

bool Watchdog::loadConfig() {
    try {
        std::ifstream f(configPath_);
        if (!f.is_open()) return false;
        json j;
        f >> j;
        config_ = j.get<Config>();
        return true;
    } catch (...) {
        return false;
    }
}

void Watchdog::startPlayer() {
    if (player_pid_ > 0) return;

    pid_t pid = fork();
    if (pid == 0) {
        // 子进程：播放器模式
        // 使用传入的 exePath_ 启动自身
        char* const args[] = {(char*)exePath_.c_str(), (char*)"--player", (char*)configPath_.c_str(), nullptr};
        execvp(args[0], args);
        // 如果 execvp 失败
        std::cerr << "[Watchdog] 启动播放器进程失败: " << errno << std::endl;
        exit(1);
    } else if (pid > 0) {
        player_pid_ = pid;
        last_heartbeat_time_ = getCurrentTimestamp();
        std::cout << "[Watchdog] 已启动播放器进程 (PID: " << player_pid_ << ")" << std::endl;
    } else {
        std::cerr << "[Watchdog] Fork 失败" << std::endl;
    }
}

void Watchdog::stopPlayer() {
    if (player_pid_ > 0) {
        std::cout << "[Watchdog] 正在停止播放器进程 (PID: " << player_pid_ << ")" << std::endl;
        kill(player_pid_, SIGTERM);
        int status;
        waitpid(player_pid_, &status, 0);
        player_pid_ = -1;
    }
}

void Watchdog::run() {
    std::cout << "[Watchdog] 守护进程启动..." << std::endl;

    // 1. 启动本地心跳监听服务器 (UDP)
    std::thread localSrv(&Watchdog::localHeartbeatServer, this);
    localSrv.detach();

    // 2. 启动云端 WebSocket 连接 (接管心跳和指令)
    if (!config_.gateway_ws_url.empty()) {
        network_->startGatewayConnection(
            config_.gateway_ws_url,
            config_.device_id,
            config_.token,
            [this](int limit) { 
                // 从数据库读取日志用于上报
                try {
                    std::string sql = "SELECT * FROM log WHERE uploaded = 0 ORDER BY created_at ASC LIMIT " + std::to_string(limit) + ";";
                    auto results = db_->query(sql);
                    json logs = json::array();
                    for (const auto& row : results) {
                        logs.push_back(row); // 简化处理，直接透传数据库行
                    }
                    return logs;
                } catch (...) { return json::array(); }
            },
            [this](const std::vector<std::string>& logIds) {
                // 更新日志上报状态
                try {
                    std::string ids;
                    for (size_t i = 0; i < logIds.size(); ++i) {
                        ids += "'" + logIds[i] + "'" + (i == logIds.size() - 1 ? "" : ",");
                    }
                    db_->execute("UPDATE log SET uploaded = 1 WHERE log_id IN (" + ids + ");");
                } catch (...) {}
            },
            [this](const json& msg, std::function<void(const json&)> send) {
                this->handleCloudCommand(msg, send);
            }
        );
    }

    // 3. 首次启动播放器
    startPlayer();

    // 4. 进入监控循环
    monitorLoop();
}

void Watchdog::monitorLoop() {
    while (!should_exit_) {
        std::this_thread::sleep_for(std::chrono::seconds(5));

        // 1. 检查进程是否还在
        if (player_pid_ > 0) {
            int status;
            pid_t result = waitpid(player_pid_, &status, WNOHANG);
            if (result == -1) {
                logFault("CRASH", "播放器进程异常退出");
                player_pid_ = -1;
                startPlayer();
            } else if (result > 0) {
                // 进程已退出
                if (WIFEXITED(status)) {
                    std::cout << "[Watchdog] 播放器进程正常退出 (Status: " << WEXITSTATUS(status) << ")" << std::endl;
                } else if (WIFSIGNALED(status)) {
                    std::cout << "[Watchdog] 播放器进程被信号终止 (Signal: " << WTERMSIG(status) << ")" << std::endl;
                    logFault("CRASH", "播放器进程被信号终止");
                }
                player_pid_ = -1;
                startPlayer();
            } else {
                // 进程还在，检查心跳超时
                long long now = getCurrentTimestamp();
                if (now - last_heartbeat_time_ > 30) {
                    std::cout << "[Watchdog] 播放器心跳超时 (30s)，强制重启" << std::endl;
                    logFault("HANG", "播放器心跳超时");
                    stopPlayer();
                    startPlayer();
                }
            }
        } else {
            startPlayer();
        }
    }
}

void Watchdog::localHeartbeatServer() {
    int sockfd = socket(AF_INET, SOCK_DGRAM, 0);
    if (sockfd < 0) return;

    struct sockaddr_in servaddr;
    servaddr.sin_family = AF_INET;
    servaddr.sin_addr.s_addr = INADDR_ANY;
    servaddr.sin_port = htons(WD_HEARTBEAT_PORT);

    if (bind(sockfd, (const struct sockaddr *)&servaddr, sizeof(servaddr)) < 0) {
        close(sockfd);
        return;
    }

    char buffer[1024];
    struct sockaddr_in cliaddr;
    socklen_t len = sizeof(cliaddr);

    while (!should_exit_) {
        int n = recvfrom(sockfd, (char *)buffer, 1024, 0, (struct sockaddr *) &cliaddr, &len);
        if (n > 0) {
            std::string msg(buffer, n);
            if (msg == "HEARTBEAT") {
                last_heartbeat_time_ = getCurrentTimestamp();
            }
        }
    }
    close(sockfd);
}

void Watchdog::logFault(const std::string& type, const std::string& message) {
    if (!db_) return;
    try {
        std::string logId = generateUUID();
        long long now = getCurrentTimestamp();
        std::string sql = "INSERT INTO log (log_id, device_id, ad_id, ad_file_name, status_code, status_msg, created_at, uploaded) VALUES ('"
            + logId + "', '" + config_.device_id + "', 'SYSTEM', 'WATCHDOG', 500, '" + type + ": " + message + "', " + std::to_string(now) + ", 0);";
        db_->execute(sql);
        std::cout << "[Watchdog] 已记录故障: " << type << " - " << message << std::endl;
    } catch (...) {}
}

void Watchdog::handleCloudCommand(const json& msg, std::function<void(const json&)> send) {
    std::string type = msg.value("type", "");
    std::string payload = msg.value("payload", "");

    if (type == "command" && payload == "REBOOT") {
        std::cout << "[Watchdog] 收到云端软重启指令" << std::endl;
        logFault("RESTART", "收到云端重启指令");
        stopPlayer();
        startPlayer();
        
        json resp;
        resp["type"] = "command_response";
        resp["device_id"] = config_.device_id;
        resp["ts"] = getCurrentTimestamp();
        resp["payload"] = {{"status", "success"}, {"result", "rebooting"}};
        send(resp);
    } else {
        // 转发指令到播放器 (UDP 9998)
        std::cout << "[Watchdog] 转发指令到播放器: " << type << " " << payload << std::endl;
        
        int sockfd = socket(AF_INET, SOCK_DGRAM, 0);
        if (sockfd >= 0) {
            struct sockaddr_in servaddr;
            servaddr.sin_family = AF_INET;
            servaddr.sin_port = htons(9998);
            servaddr.sin_addr.s_addr = inet_addr("127.0.0.1");

            std::string s = msg.dump();
            sendto(sockfd, s.c_str(), s.length(), 0, (const struct sockaddr *)&servaddr, sizeof(servaddr));

            // 等待播放器回执 (简单实现，阻塞 1s 等待 UDP 回包)
            struct timeval tv;
            tv.tv_sec = 1;
            tv.tv_usec = 0;
            setsockopt(sockfd, SOL_SOCKET, SO_RCVTIMEO, (const char*)&tv, sizeof tv);

            char buffer[2048];
            int n = recv(sockfd, buffer, 2048, 0);
            if (n > 0) {
                try {
                    json reply = json::parse(std::string(buffer, n));
                    send(reply);
                    std::cout << "[Watchdog] 转发指令回执成功" << std::endl;
                } catch (...) {}
            }
            close(sockfd);
        }
    }
}

long long Watchdog::getCurrentTimestamp() {
    return std::chrono::system_clock::to_time_t(std::chrono::system_clock::now());
}

std::string Watchdog::generateUUID() {
    static const char hex_chars[] = "0123456789ABCDEF";
    std::random_device rd;
    std::mt19937 gen(rd());
    std::uniform_int_distribution<> dis(0, 15);
    std::string uuid;
    for (int i = 0; i < 4; ++i) {
        for (int j = 0; j < 4; ++j) uuid += hex_chars[dis(gen)];
        if (i < 3) uuid += "-";
    }
    return uuid;
}
