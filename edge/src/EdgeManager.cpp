#include "EdgeManager.hpp"
#include "Advertisement.hpp"
#include "Schedule.hpp"
#include "PlayItem.hpp"
#include <iostream>
#include <fstream>
#include <sstream>
#include <ctime>
#include <iomanip>
#include <algorithm>
#include <thread> // 增加 thread 头文件
#include <chrono> // 增加 chrono 头文件
#include <filesystem>
#include <random> // 增加 random 头文件
#ifdef _WIN32
#else
#include <ifaddrs.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#endif

static std::string b64encode(const std::vector<uint8_t>& in) {
    static const char* tbl = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    std::string out;
    size_t i = 0;
    while (i + 2 < in.size()) {
        uint32_t n = (in[i] << 16) | (in[i + 1] << 8) | in[i + 2];
        out.push_back(tbl[(n >> 18) & 63]);
        out.push_back(tbl[(n >> 12) & 63]);
        out.push_back(tbl[(n >> 6) & 63]);
        out.push_back(tbl[n & 63]);
        i += 3;
    }
    if (i + 1 == in.size()) {
        uint32_t n = (in[i] << 16);
        out.push_back(tbl[(n >> 18) & 63]);
        out.push_back(tbl[(n >> 12) & 63]);
        out.push_back('=');
        out.push_back('=');
    } else if (i + 2 == in.size()) {
        uint32_t n = (in[i] << 16) | (in[i + 1] << 8);
        out.push_back(tbl[(n >> 18) & 63]);
        out.push_back(tbl[(n >> 12) & 63]);
        out.push_back(tbl[(n >> 6) & 63]);
        out.push_back('=');
    }
    return out;
}
void EdgeManager::handleCloudCommand(const json& msg, std::function<void(const json&)> send) {
    bool is_snapshot = (msg.contains("type") && msg["type"] == "snapshot_request") ||
        (msg.contains("type") && msg["type"] == "command" && msg.contains("payload") && msg["payload"] == "SNAPSHOT");
    bool is_command = (msg.contains("type") && msg["type"] == "command") && !is_snapshot;
    
    if (is_snapshot) {
        std::string req_id = msg.value("cmd_id", "");
        if (req_id.empty()) req_id = msg.value("req_id", "");
        
        printInfo(LogLevel::INFO, "[云端指令] 收到截图指令，请求ID: " + req_id);
        
        std::string path = config_.resources_dir + "snapshot.bmp";
        bool ok = false;
        if (player_) {
            ok = player_->CaptureSnapshotBMP(path);
        }
        
        if (ok) {
            printInfo(LogLevel::INFO, "[云端指令] 截图成功，已保存至: " + path);
        } else {
            printInfo(LogLevel::ERROR, "[云端指令] 截图失败");
        }
        
        std::vector<uint8_t> bytes;
        if (ok) {
            std::ifstream f(path, std::ios::binary);
            bytes = std::vector<uint8_t>(std::istreambuf_iterator<char>(f), std::istreambuf_iterator<char>());
        }
        std::string b64 = bytes.empty() ? "" : b64encode(bytes);
        json snapshot_msg;
        snapshot_msg["type"] = "snapshot_response";
        snapshot_msg["device_id"] = config_.device_id;
        snapshot_msg["req_id"] = req_id;
        snapshot_msg["ts"] = static_cast<long long>(std::time(nullptr));
        snapshot_msg["payload"] = { {"format","bmp"},{"data", b64} };
        send(snapshot_msg);
    } else if (is_command) {
        std::string cmd = msg.value("payload", "");
        std::string cmd_id = msg.value("cmd_id", "");
        json data = msg.value("data", json::object());
        
        printInfo(LogLevel::INFO, "[云端指令] 收到通用指令: " + cmd + ", 参数: " + data.dump());
        
        std::string result = "ok";
        if (cmd == "SET_VOLUME") {
            int old_vol = current_volume_;
            bool old_mute = current_mute_;
            int vol = data.value("volume", current_volume_);
            bool mute = data.value("mute", current_mute_);
            current_volume_ = vol;
            current_mute_ = mute;
            result = std::string("set_volume:") + std::to_string(vol) + "|mute:" + (mute ? "1" : "0");
            
            printInfo(LogLevel::INFO, "[云端指令] 执行完成 SET_VOLUME - 执行前: (音量=" + std::to_string(old_vol) + ", 静音=" + (old_mute ? "是" : "否") + 
                      ") -> 执行后: (音量=" + std::to_string(vol) + ", 静音=" + (mute ? "是" : "否") + ")");
        } else if (cmd == "REBOOT") {
            result = "reboot_ok";
            should_soft_reboot_ = true;
            printInfo(LogLevel::INFO, "[云端指令] 执行 REBOOT，设备即将软重启");
        } else {
            result = cmd + "_ok";
            printInfo(LogLevel::INFO, "[云端指令] 未知指令或无需处理的指令: " + cmd);
        }
        json resp;
        resp["type"] = "command_response";
        resp["device_id"] = config_.device_id;
        resp["req_id"] = msg.value("req_id", "");
        resp["ts"] = static_cast<long long>(std::time(nullptr));
        resp["payload"] = { {"cmd_id", cmd_id}, {"status","success"}, {"result", result} };
        send(resp);
        printInfo(LogLevel::INFO, "[云端指令] 回执已发送，指令ID: " + cmd_id);
    }
}

EdgeManager::EdgeManager() : is_initialized_(false) {
}

EdgeManager::~EdgeManager() {
    // 停止网络客户端
    if (network_) {
        network_->stopGatewayConnection();
    }

    if (player_) {
        player_->CloseWindow();
    }
    SDL_Quit();
}

bool EdgeManager::init(const std::string& configPath) {
    if (is_initialized_) {
        printInfo(LogLevel::WARNING, "EdgeManager 已经初始化过了");
        return true;
    }

    printInfo(LogLevel::INFO, "正在初始化 EdgeManager...");

    // 1. 加载配置文件
    if (!loadConfig(configPath)) {
        printInfo(LogLevel::ERROR, "加载配置文件失败: " + configPath);
        return false;
    }

    // 2. 初始化数据库
    if (!initDatabase()) {
        printInfo(LogLevel::ERROR, "初始化数据库失败");
        return false;
    }

    // 4. 加载广告素材数据
    if (!syncAds()) {
        printInfo(LogLevel::ERROR, "同步广告数据失败");
        return false;
    }
    printInfo(LogLevel::INFO, "广告数据已入库");

    // 5. 加载排期策略数据
    if (!syncSchedule()) {
        printInfo(LogLevel::ERROR, "同步排期数据失败");
        return false;
    }
    printInfo(LogLevel::INFO, "排期数据已入库");

    // 6. 初始化播放器
    // 创建 VideoPlayer 实例，后续将用于加载和播放媒体文件
    player_ = std::make_unique<VideoPlayer>();

    is_initialized_ = true;
    
    // 7. 初始化播放列表 (检查素材完整性)
    // 预先检查排期中引用的所有素材文件是否存在，避免播放时出错
    if (!initPlaylist()) {
        printInfo(LogLevel::WARNING, "播放列表初始化存在问题");
    }

    // 8. 启动网络客户端 
    // 如果配置了云端 API 地址，则初始化 NetworkClient 并启动后台上报线程
    if (!config_.gateway_ws_url.empty()) {
        network_ = std::make_unique<NetworkClient>(config_.gateway_ws_url);
        
        // 读取上报间隔
        int interval = 10;
        try {
            auto items = db_->query("SELECT report_interval_sec FROM schedule LIMIT 1;");
            if (!items.empty()) {
                int dbInterval = std::stoi(items[0].at("report_interval_sec"));
                if (dbInterval > 0) interval = dbInterval;
            }
        } catch (...) {}

        // 启动网关连接
        // 建立 WebSocket 长连接，用于接收服务端的实时指令
        if (!config_.gateway_ws_url.empty() && !config_.device_id.empty()) {
            network_->startGatewayConnection(
                config_.gateway_ws_url,
                config_.device_id,
                config_.token,
                [this](int limit) { return this->getLogs(limit); },
                [this](const std::vector<std::string>& logIds) { this->updateLogStatus(logIds, 1); },
                [this](const json& msg, std::function<void(const json&)> send) {
                    this->handleCloudCommand(msg, send);
                }
            );
        }
    }

    // 9. 检查并清理存储空间
    cleanupStorage();

    printInfo(LogLevel::INFO, "EdgeManager 初始化完成");

    return true;
}

// 辅助函数：判断时间是否在范围内
bool isTimeInRange(const std::string& now, const std::string& range) {
    size_t dash = range.find('-');
    if (dash == std::string::npos) return false;
    
    std::string start = range.substr(0, dash);
    std::string end = range.substr(dash + 1);
    
    return now >= start && now <= end;
}

void EdgeManager::run() {
    printInfo(LogLevel::INFO, "进入主循环...");
    
    // 初始化 SDL (只需一次)
    if (SDL_Init(SDL_INIT_VIDEO | SDL_INIT_AUDIO | SDL_INIT_TIMER) < 0) {
        printInfo(LogLevel::ERROR, "无法初始化 SDL: " + std::string(SDL_GetError()));
        return;
    }

    // 创建播放窗口 (复用)
    player_->CreateWindow("Edge Player", 1280, 720);

    // 主循环
    // 这是一个死循环，直到程序收到退出信号。
    // 主要职责：
    // 1. 获取下一个播放任务 (getNextAsset)
    // 2. 调用 player_->Load 和 player_->Play
    // 3. 在播放过程中持续调用 player_->Update (渲染画面)
    // 4. 监控窗口状态，处理意外关闭
    while (true) {
        if (should_soft_reboot_) {
            printInfo(LogLevel::INFO, "执行软重启：断开网关连接，关闭播放器，再次上线");
            try {
                if (network_) {
                    network_->stopGatewayConnection();
                }
                if (player_) {
                    player_->Stop();
                    player_->CloseWindow();
                }
                SDL_Quit();
            } catch (...) {}
            if (SDL_Init(SDL_INIT_VIDEO | SDL_INIT_AUDIO | SDL_INIT_TIMER) < 0) {
                printInfo(LogLevel::ERROR, "软重启后无法初始化 SDL: " + std::string(SDL_GetError()));
            } else {
                player_->CreateWindow("Edge Player", 1280, 720);
                if (!config_.gateway_ws_url.empty() && !config_.device_id.empty()) {
                    if (!network_) {
                        network_ = std::make_unique<NetworkClient>(config_.gateway_ws_url);
                    }
                    network_->startGatewayConnection(
                        config_.gateway_ws_url,
                        config_.device_id,
                        config_.token,
                        [this](int limit) { return this->getLogs(limit); },
                        [this](const std::vector<std::string>& logIds) { this->updateLogStatus(logIds, 1); },
                        [this](const json& msg, std::function<void(const json&)> send) {
                            this->handleCloudCommand(msg, send);
                        }
                    );
                }
            }
            should_soft_reboot_ = false;
        }
        if (should_exit_) {
            goto end_loop;
        }
        // 检查是否有退出信号 (暂时没有实现信号处理，这里是一个死循环)
        // 实际项目中应该有退出机制

        // 获取下一个播放素材
        // 参数 true 表示允许插播 (Interrupt)
        auto item = getNextAsset(); 
        
        if (item) {
            printInfo(LogLevel::INFO, "开始播放: " + item->getAdId() + " (" + item->getFilePath() + ")");
            
            // 记录开始播放时间
            long long startTime = std::time(nullptr);

            // 1. 记录播放开始 (写入 playlist 表)
            recordPlayStart(*item);
            
            // 2. 准备播放
            player_->SetWindowTitle("Playing: " + item->getAdId());
            int64_t duration_ms = item->getDuration() * 1000;
            
            // 加载媒体文件
            if (player_->Load(item->getFilePath(), duration_ms)) {
                // 开始播放 (启动解码线程)
                if (!player_->Play()) {
                    printInfo(LogLevel::ERROR, "播放失败: " + item->getAdId());
                } else {
                    // 等待播放结束
                    // 这是一个阻塞循环，但必须在其中不断调用 Update 以刷新 UI
                    while (player_->IsPlaying()) {
                        // 核心渲染调用：处理 SDL 事件并刷新纹理
                        player_->Update();
                        
                        // 稍微休眠，释放 CPU，具体休眠时间由 VideoPlayer 内部帧率控制决定，这里只是为了防止空转过快
                        std::this_thread::sleep_for(std::chrono::milliseconds(1));
                        
                        // 实时检查指令与退出状态
                        if (should_soft_reboot_) {
                             player_->Stop();
                             printInfo(LogLevel::INFO, "检测到重启指令 (播放中)，停止播放并执行重启");
                             break; 
                        }
                        if (should_exit_) {
                             player_->Stop();
                             goto end_loop;
                        }
                        // 实时检查窗口状态
                        // 如果用户手动关闭了窗口，这里需要感知并退出
                        if (!player_->IsWindowOpen()) {
                             player_->Stop();
                             printInfo(LogLevel::INFO, "检测到窗口关闭 (播放中)，准备退出");
                             goto end_loop;
                        }
                    }
                }
            } else {
                printInfo(LogLevel::WARNING, "加载失败: " + item->getFilePath());
            }
            
            // 再次检查窗口状态 (防止在 Load 失败或 Play 刚结束的瞬间关闭)
            if (!player_->IsWindowOpen()) {
                printInfo(LogLevel::INFO, "检测到窗口关闭 (播放间隙)，准备退出");
                goto end_loop;
            }
            
            // 3. 记录播放结束 (写入 log 表)
            recordPlayEnd(*item, startTime, duration_ms);

        } else {
            // 没有可播放的内容，休眠一会避免空转
            printInfo(LogLevel::WARNING, "当前没有可播放的排期，休眠 5秒...");
            
            if (!waitForPlaybackOrStop()) {
                printInfo(LogLevel::INFO, "休眠期间收到退出信号，但保持程序继续运行");
            }
        }

        // 简单处理 SDL 事件，防止窗口无响应
        SDL_Event event;
        while (SDL_PollEvent(&event)) {
            if (event.type == SDL_QUIT) {
                printInfo(LogLevel::INFO, "收到退出事件，准备退出");
                should_exit_ = true;
                goto end_loop;
            }
        }
    }

end_loop:
    printInfo(LogLevel::INFO, "退出主循环");
    
    player_->CloseWindow();
    
    if (network_) {
        network_->stopGatewayConnection();
    }

    SDL_Quit();
}

const Config& EdgeManager::getConfig() const {
    return config_;
}

bool EdgeManager::loadConfig(const std::string& configPath) {
    try {
        std::ifstream f(configPath);
        if (!f.is_open()) {
            std::cerr << "无法打开配置文件: " << configPath << std::endl;
            return false;
        }

        json j;
        f >> j;
        config_ = j.get<Config>();
        
        std::cout << "配置已加载:" << std::endl;
        return true;
    } catch (const std::exception& e) {
        std::cerr << "解析配置文件异常: " << e.what() << std::endl;
        return false;
    }
}

std::string EdgeManager::getCurrentTimeStr() {
    auto now = std::chrono::system_clock::now();
    std::time_t now_c = std::chrono::system_clock::to_time_t(now);
    std::tm* local_tm = std::localtime(&now_c);
    
    std::stringstream ss;
    ss << std::put_time(local_tm, "%H:%M:%S");
    return ss.str();
}

bool EdgeManager::isTimeInSlot(const std::string& timeRange) {
    size_t dashPos = timeRange.find('-');
    if (dashPos == std::string::npos) return false;

    std::string startStr = timeRange.substr(0, dashPos);
    std::string endStr = timeRange.substr(dashPos + 1);
    std::string nowStr = getCurrentTimeStr();

    return (nowStr >= startStr && nowStr <= endStr);
}

//内部辅助方法

void EdgeManager::recordPlayStart(const PlayItem& item) {
    if (!db_) return;

    try {
        // 转义文件路径，防止 SQL 注入
        std::string safePath = item.getFilePath();
        size_t pos = 0;
        while ((pos = safePath.find("'", pos)) != std::string::npos) {
            safePath.replace(pos, 1, "''");
            pos += 2;
        }

        // 使用事务，保证操作原子性
        db_->beginTransaction();

        // 1. 插入当前播放记录
        std::string sql = "INSERT INTO playlist (ad_id, file_path, type, duration, volume, priority) VALUES ('"
            + item.getAdId() + "', '"
            + safePath + "', '"
            + item.getType() + "', "
            + std::to_string(item.getDuration()) + ", "
            + std::to_string(item.getVolume()) + ", "
            + std::to_string(item.getPriority()) + ");";
        db_->execute(sql);
        
        // 2. 清理旧记录 (保留最近 50 条)
        db_->execute("DELETE FROM playlist WHERE id NOT IN (SELECT id FROM playlist ORDER BY id DESC LIMIT 50);");

        db_->commit();

    } catch (const std::exception& e) {
        db_->rollback(); // 发生异常回滚
        printInfo(LogLevel::ERROR, "记录播放开始失败: " + std::string(e.what()));
    }
}

void EdgeManager::recordPlayEnd(const PlayItem& item, long long startTime, int durationMs, int statusCode) {
    if (!db_) return;
    
    // 1. 播放结束日志
    printInfo(LogLevel::INFO, "播放结束: " + item.getAdId());
    
    // 2. 记录详细日志到数据库 (log 表)
    long long endTime = std::time(nullptr);
    std::string statusMsg = (statusCode == 200) ? "Play Success" : "Play Failed";
    
    // 调用现有的 log 方法写入 log 表
    log(item.getAdId(), item.getFilePath(), startTime, endTime, durationMs, statusCode, statusMsg);
    
    // 3. 更新状态 (使用事务)
    try {
        db_->beginTransaction();
        
        // 更新 last_played_time
        db_->execute("UPDATE advertisement SET last_played_time = " + std::to_string(endTime) + " WHERE ad_id = '" + item.getAdId() + "';");

        // 如果是插播素材，更新 schedule_interrupt 表的状态为已播放
        db_->execute("UPDATE schedule_interrupt SET status = 1 WHERE ad_id = '" + item.getAdId() + "' AND status = 0;");
        
        db_->commit();
    } catch (const std::exception& e) {
        db_->rollback();
        printInfo(LogLevel::ERROR, "更新播放状态失败: " + std::string(e.what()));
    }
}

bool EdgeManager::waitForPlaybackOrStop() {
    // 分段休眠并处理事件，确保能响应退出
    for (int i = 0; i < 50; ++i) {
        if (should_exit_ || should_soft_reboot_) {
            return false;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
        SDL_Event event;
        while (SDL_PollEvent(&event)) {
            if (event.type == SDL_QUIT) {
                should_exit_ = true;
                return false; // 收到退出信号
            }
        }
    }
    return true; // 继续
}

std::unique_ptr<PlayItem> EdgeManager::getNextAsset() {
    if (!db_) return nullptr;

    std::string now = getCurrentTimeStr();

    // 1. 检查插播 (Interrupt) - 优先级最高
    // 假设插播是全局的，只要有 trigger_type='emergency' 或者满足特定条件
    // 这里简单实现：查询 schedule_interrupt 表中 trigger_type='emergency' 的
    // 或者根据业务逻辑，如果有未播放的插播任务 (status = 0)
    
    try {
        // 按优先级降序查询未播放的插播任务
        std::string sql = "SELECT * FROM schedule_interrupt WHERE status = 0 ORDER BY priority DESC LIMIT 1;";
        auto interrupts = db_->query(sql);
        if (!interrupts.empty()) {
            auto& row = interrupts[0];
            std::string adId = row.at("ad_id");
            
            // 查询素材详情
            std::string adSql = "SELECT * FROM advertisement WHERE ad_id = '" + adId + "';";
            auto ads = db_->query(adSql);
            if (!ads.empty()) {
                auto& adRow = ads[0];
                std::string filePath = config_.resources_dir + "ads/" + adRow.at("filename");
                
                auto item = std::make_unique<PlayItem>(
                    adId, filePath, 
                    adRow.at("type"), 
                    std::stoi(adRow.at("duration")), 
                    60, // volume 默认 60
                    std::stoi(row.at("priority"))
                );
                
                printInfo(LogLevel::INFO, "获取到插播素材: " + adId);
                return item;
            }
        }
    } catch (const std::exception& e) {
        printInfo(LogLevel::ERROR, "查询插播失败: " + std::string(e.what()));
    }

    // 2. 检查时间段 (TimeSlot) - 定投/轮播
    try {
        std::string sql = "SELECT * FROM schedule_timeslot ORDER BY priority DESC;";
        auto slots = db_->query(sql);
        
        for (const auto& row : slots) {
            std::string timeRange = row.at("time_range");
            // 检查当前时间是否在范围内
            if (isTimeInRange(now, timeRange)) {
                int slotId = std::stoi(row.at("slot_id"));
                
                // 如果切换了 timeslot，重置索引
                if (slotId != last_timeslot_id_) {
                    current_playlist_index_ = 0;
                    last_timeslot_id_ = slotId;
                }
                
                // 解析 playlist JSON
                std::string playlistStr = row.at("playlist");
                json playlistJson = json::parse(playlistStr);
                
                if (playlistJson.empty()) continue;
                
                // 获取当前索引的素材 ID
                if (current_playlist_index_ >= playlistJson.size()) {
                    current_playlist_index_ = 0; // 循环
                }
                
                std::string adId = playlistJson[current_playlist_index_].get<std::string>();
                
                // 查询素材详情
                std::string adSql = "SELECT * FROM advertisement WHERE ad_id = '" + adId + "';";
                auto ads = db_->query(adSql);
                if (!ads.empty()) {
                    auto& adRow = ads[0];
                    std::string filePath = config_.resources_dir + "ads/" + adRow.at("filename");
                    int volume = std::stoi(row.at("volume"));
                    int priority = std::stoi(row.at("priority"));
                    
                    auto item = std::make_unique<PlayItem>(
                        adId, filePath, 
                        adRow.at("type"), 
                        std::stoi(adRow.at("duration")), 
                        volume,
                        priority
                    );
                    
                    // 递增索引，为下一次调用做准备
                    current_playlist_index_++;
                    
                    return item;
                } else {
                    printInfo(LogLevel::WARNING, "素材未找到: " + adId);
                    current_playlist_index_++; // 即使没找到也要跳过，避免死循环
                }
            }
        }
    } catch (const std::exception& e) {
        printInfo(LogLevel::ERROR, "查询排期失败: " + std::string(e.what()));
    }
    
    return nullptr; // 没有可播放的内容
}

bool EdgeManager::initPlaylist() {
    printInfo(LogLevel::INFO, "初始化播放列表: 检查排期和素材完整性...");
    
    // 1. 获取所有排期 TimeSlots
    try {
        std::string sql = "SELECT * FROM schedule_timeslot ORDER BY priority DESC;";
        auto slots = db_->query(sql);
        
        if (slots.empty()) {
            printInfo(LogLevel::WARNING, "排期表为空，请检查 Schedule.json 是否正确加载");
            return false;
        }

        int missingCount = 0;
        int totalCount = 0;

        for (const auto& row : slots) {
            std::string playlistStr = row.at("playlist");
            json playlistJson = json::parse(playlistStr);
            
            for (const auto& item : playlistJson) {
                std::string adId = item.get<std::string>();
                totalCount++;
                
                // 检查素材是否在数据库中
                auto ads = db_->query("SELECT filename FROM advertisement WHERE ad_id = '" + adId + "';");
                if (ads.empty()) {
                    printInfo(LogLevel::ERROR, "素材未在数据库中注册: " + adId);
                    missingCount++;
                    continue;
                }
                
                // 检查文件是否存在
                std::string filename = ads[0].at("filename");
                std::string filePath = config_.resources_dir + "ads/" + filename;
                if (!std::filesystem::exists(filePath)) {
                    printInfo(LogLevel::WARNING, "素材文件缺失: " + filePath);
                    missingCount++;
                }
            }
        }
        
        printInfo(LogLevel::INFO, "排期检查完成: 共 " + std::to_string(totalCount) + " 个素材，缺失 " + std::to_string(missingCount) + " 个");
        return missingCount == 0; // 如果有缺失，返回 false

    } catch (const std::exception& e) {
        printInfo(LogLevel::ERROR, "初始化播放列表异常: " + std::string(e.what()));
        return false;
    }
}

void EdgeManager::cleanupStorage() {
    long long maxSizeBytes = 5LL * 1024 * 1024 * 1024; // 5GB
    long long currentSize = 0;
    
    // 1. 计算当前文件夹大小
    try {
        for (const auto& entry : std::filesystem::recursive_directory_iterator(config_.resources_dir)) {
            if (std::filesystem::is_regular_file(entry)) {
                currentSize += std::filesystem::file_size(entry);
            }
        }
    } catch (const std::exception& e) {
        printInfo(LogLevel::ERROR, "计算磁盘空间失败: " + std::string(e.what()));
        return;
    }

    std::cout << "当前磁盘占用: " << currentSize << " 字节 (阈值: " << maxSizeBytes << ")" << std::endl;

    if (currentSize <= maxSizeBytes) {
        std::cout << "磁盘空间充足，无需清理" << std::endl;
        return;
    }

    printInfo(LogLevel::WARNING, "磁盘空间不足，开始清理 (LRU)...");

    // 2. 查询需要删除的文件 (按 last_played_time 升序)
    try {
        std::string sql = "SELECT ad_id, filename, bytes FROM advertisement ORDER BY last_played_time ASC;";
        auto results = db_->query(sql);

        for (const auto& row : results) {
            if (currentSize <= maxSizeBytes / 2) { // 清理到 50%
                break;
            }

            std::string adId = row.at("ad_id");
            std::string filename = row.at("filename");
            long long bytes = std::stoll(row.at("bytes"));
            
            std::string filePath = config_.resources_dir + "ads/" + filename; // 假设都在 ads 目录下
            
            // 删除文件
            if (std::filesystem::exists(filePath)) {
                std::filesystem::remove(filePath);
                printInfo(LogLevel::INFO, "已删除文件: " + filename);
                currentSize -= bytes;
            } else {
                printInfo(LogLevel::WARNING, "文件不存在: " + filename);
            }

            // 从数据库删除记录
            db_->execute("DELETE FROM advertisement WHERE ad_id = '" + adId + "';");
        }
        
        printInfo(LogLevel::INFO, "清理完成，当前占用: " + std::to_string(currentSize));

    } catch (const std::exception& e) {
        printInfo(LogLevel::ERROR, "清理磁盘空间异常: " + std::string(e.what()));
    }
}

void EdgeManager::updateLogStatus(const std::vector<std::string>& logIds, int status) {
    if (!db_ || logIds.empty()) return;

    try {
        std::string idsStr;
        for (size_t i = 0; i < logIds.size(); ++i) {
            idsStr += "'" + logIds[i] + "'";
            if (i < logIds.size() - 1) idsStr += ",";
        }

        std::string sql = "UPDATE log SET uploaded = " + std::to_string(status) + " WHERE log_id IN (" + idsStr + ");";
        db_->execute(sql);

    } catch (const std::exception& e) {
        printInfo(LogLevel::ERROR, "更新日志状态失败: " + std::string(e.what()));
    }
}

// 辅助函数：获取本机 IP
std::string getLocalIPAddress() {
#ifdef _WIN32
    std::string ipAddress = "127.0.0.1";
    WSADATA wsaData;
    if (WSAStartup(MAKEWORD(2, 2), &wsaData) != 0) {
        return ipAddress;
    }
    char host[256] = {0};
    if (gethostname(host, sizeof(host)) == 0) {
        addrinfo hints = {};
        hints.ai_family = AF_INET;
        hints.ai_socktype = SOCK_STREAM;
        addrinfo* res = nullptr;
        if (getaddrinfo(host, nullptr, &hints, &res) == 0) {
            for (addrinfo* p = res; p != nullptr; p = p->ai_next) {
                sockaddr_in* addr = reinterpret_cast<sockaddr_in*>(p->ai_addr);
                char ipStr[INET_ADDRSTRLEN] = {0};
                inet_ntop(AF_INET, &addr->sin_addr, ipStr, INET_ADDRSTRLEN);
                std::string ip(ipStr);
                if (ip != "127.0.0.1") {
                    ipAddress = ip;
                    break;
                }
            }
            freeaddrinfo(res);
        }
    }
    WSACleanup();
    return ipAddress;
#else
    std::string ipAddress = "127.0.0.1";
    struct ifaddrs *interfaces = nullptr;
    
    if (getifaddrs(&interfaces) == 0) {
        for (struct ifaddrs *temp_addr = interfaces; temp_addr != nullptr; temp_addr = temp_addr->ifa_next) {
            if (temp_addr->ifa_addr && temp_addr->ifa_addr->sa_family == AF_INET) {
                char ipStr[INET_ADDRSTRLEN];
                void* addrPtr = &((struct sockaddr_in*)temp_addr->ifa_addr)->sin_addr;
                inet_ntop(AF_INET, addrPtr, ipStr, INET_ADDRSTRLEN);
                
                std::string ip(ipStr);
                if (ip != "127.0.0.1") {
                    ipAddress = ip;
                    break; // Found a non-loopback address
                }
            }
        }
        freeifaddrs(interfaces);
    }
    return ipAddress;
#endif
}

void EdgeManager::log(const std::string& adId, const std::string& adFileName, long long startTime, long long endTime, int durationMs, int statusCode, const std::string& statusMsg) {
    if (!db_) return;

    try {
        // 生成 16位 UUID (XXXX-XXXX-XXXX-XXXX)
        std::string logId;
        static const char hex_chars[] = "0123456789ABCDEF";
        std::random_device rd;
        std::mt19937 gen(rd());
        std::uniform_int_distribution<> dis(0, 15);

        for (int i = 0; i < 4; ++i) {
            for (int j = 0; j < 4; ++j) {
                logId += hex_chars[dis(gen)];
            }
            if (i < 3) logId += "-";
        }

        long long createdAt = std::time(nullptr);
        std::string deviceId = config_.device_id;
        std::string firmwareVersion = "1.0.0"; // 假设版本
        std::string deviceIp = getLocalIPAddress();    // 获取本机真实IP

        // 格式化时间戳
        auto formatTime = [](long long t) {
            std::time_t tt = static_cast<std::time_t>(t);
            std::tm* tm = std::localtime(&tt);
            std::stringstream ss;
            ss << std::put_time(tm, "%Y-%m-%d %H:%M:%S");
            return ss.str();
        };

        std::string sql = "INSERT INTO log (log_id, device_id, ad_id, ad_file_name, start_time, end_time, duration_ms, status_code, status_msg, created_at, device_ip, firmware_version, uploaded) VALUES ('"
            + logId + "', '"
            + deviceId + "', '"
            + adId + "', '"
            + adFileName + "', '"
            + formatTime(startTime) + "', '"
            + formatTime(endTime) + "', "
            + std::to_string(durationMs) + ", "
            + std::to_string(statusCode) + ", '"
            + statusMsg + "', "
            + std::to_string(createdAt) + ", '"
            + deviceIp + "', '"
            + firmwareVersion + "', 0);"; // 默认未上传
        
        db_->execute(sql);
        
        // 同时输出到控制台
        std::cout << "[LOG] " << adFileName << " (" << durationMs << "ms) - " << statusCode << std::endl;

    } catch (const std::exception& e) {
        std::cerr << "日志写入数据库失败: " << e.what() << std::endl;
    }
}

void EdgeManager::printInfo(LogLevel level, const std::string& message) {
    std::string levelStr;
    std::string colorStart;
    std::string colorEnd = "\033[0m";

    switch (level) {
        case LogLevel::INFO: 
            levelStr = "INFO"; 
            colorStart = "\033[32m"; // Green
            break;
        case LogLevel::WARNING: 
            levelStr = "WARNING"; 
            colorStart = "\033[33m"; // Yellow
            break;
        case LogLevel::ERROR: 
            levelStr = "ERROR"; 
            colorStart = "\033[31m"; // Red
            break;
        default: 
            levelStr = "UNKNOWN"; 
            colorStart = "\033[0m"; 
            break;
    }

    std::ostream& out = (level == LogLevel::ERROR) ? std::cerr : std::cout;
    
    // 获取线程ID
    std::stringstream ss;
    ss << std::this_thread::get_id();
    
    out << colorStart << "[" << getCurrentTimeStr() << "] [" << levelStr << "] [Thread:" << ss.str() << "] " << message << colorEnd << std::endl;
}

json EdgeManager::getLogs(int limit) {
    if (!db_) {
        return json::array();
    }

    try {
        // 使用新的字段排序
        // 假设表中列的顺序与 create table 一致 (实际 SELECT * 会按列定义顺序)
        // log_id, device_id, ad_id, ad_file_name, start_time, end_time, duration_ms, status_code, status_msg, created_at, device_ip, firmware_version
        std::string sql = "SELECT * FROM log WHERE uploaded = 0 ORDER BY created_at ASC LIMIT " + std::to_string(limit) + ";";
        auto results = db_->query(sql);
        
        std::vector<Log> logs;
        for (const auto& row : results) {
            Log log(
                row.at("log_id"),
                row.at("device_id"),
                row.at("ad_id"),
                row.at("ad_file_name"),
                row.at("start_time"),
                row.at("end_time"),
                std::stoi(row.at("duration_ms")),
                std::stoi(row.at("status_code")),
                row.at("status_msg"),
                std::stoll(row.at("created_at")),
                row.at("device_ip"),
                row.at("firmware_version")
            );
            logs.push_back(log);
        }
        
        return json(logs);
    } catch (const std::exception& e) {
        std::cerr << "获取日志失败: " << e.what() << std::endl;
        return json::array();
    }
}

bool EdgeManager::initDatabase() {
    try {
        std::cout << "正在连接数据库: " << config_.db_path << std::endl;
        db_ = std::make_unique<Database>(config_.db_path);

        // 0. 清空现有表结构 (根据需求，每次启动重置)
        db_->execute("DROP TABLE IF EXISTS log;");
        db_->execute("DROP TABLE IF EXISTS playlist;");
        db_->execute("DROP TABLE IF EXISTS timeslot_playlist;"); // 旧表，以防万一
        db_->execute("DROP TABLE IF EXISTS schedule_timeslot;");
        db_->execute("DROP TABLE IF EXISTS schedule_interrupt;");
        db_->execute("DROP TABLE IF EXISTS schedule;");
        db_->execute("DROP TABLE IF EXISTS advertisement;");

        // 1. 日志表 (log)
        // 存储系统运行日志
        std::string createLogTableSQL = 
            "CREATE TABLE IF NOT EXISTS log ("
            "log_id TEXT PRIMARY KEY, "
            "device_id TEXT NOT NULL, "
            "ad_id TEXT, "
            "ad_file_name TEXT NOT NULL, "
            "start_time TIMESTAMP WITH TIME ZONE, "
            "end_time TIMESTAMP WITH TIME ZONE, "
            "duration_ms INT, "
            "status_code SMALLINT, "
            "status_msg TEXT, "
            "created_at BIGINT, "
            "device_ip TEXT, " // sqlite 不支持 INET 类型，用 TEXT 代替
            "firmware_version TEXT, "
            "uploaded INTEGER DEFAULT 0"
            ");";
        db_->execute(createLogTableSQL);

        // 2. 广告素材表 (advertisement)
        std::string createAdTableSQL = 
            "CREATE TABLE IF NOT EXISTS advertisement ("
            "ad_id TEXT PRIMARY KEY, "
            "type TEXT NOT NULL, "
            "filename TEXT NOT NULL, "
            "md5 TEXT NOT NULL, "
            "duration INTEGER DEFAULT 0, "
            "bytes INTEGER DEFAULT 0, "
            "last_played_time INTEGER DEFAULT 0"
            ");";
        db_->execute(createAdTableSQL);

        // 2. 排期策略表 (schedule)
        std::string createScheduleTableSQL = 
            "CREATE TABLE IF NOT EXISTS schedule ("
            "policy_id TEXT PRIMARY KEY, "
            "effective_date TEXT, "
            "download_base_url TEXT, "
            "default_volume INTEGER, "
            "download_retry_count INTEGER, "
            "report_interval_sec INTEGER"
            ");";
        db_->execute(createScheduleTableSQL);

        // 3. 插播策略表 (schedule_interrupt)
        // 增加 status 字段: 0=未播放, 1=已播放
        std::string createInterruptTableSQL = 
            "CREATE TABLE IF NOT EXISTS schedule_interrupt ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "policy_id TEXT NOT NULL, "
            "trigger_type TEXT NOT NULL, "
            "ad_id TEXT NOT NULL, "
            "priority INTEGER, "
            "play_mode TEXT, "
            "status INTEGER DEFAULT 0, "
            "FOREIGN KEY(policy_id) REFERENCES schedule(policy_id), "
            "FOREIGN KEY(ad_id) REFERENCES advertisement(ad_id)"
            ");";
        db_->execute(createInterruptTableSQL);

        // 4. 时间段策略表 (schedule_timeslot)
        std::string createTimeSlotTableSQL = 
            "CREATE TABLE IF NOT EXISTS schedule_timeslot ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "policy_id TEXT NOT NULL, "
            "slot_id INTEGER NOT NULL, "
            "time_range TEXT NOT NULL, "
            "volume INTEGER, "
            "priority INTEGER, "
            "loop_mode TEXT, "
            "playlist TEXT, " 
            "FOREIGN KEY(policy_id) REFERENCES schedule(policy_id)"
            ");";
        db_->execute(createTimeSlotTableSQL);

        // 5. 播放列表表 (playlist)
        std::string createPlaylistTableSQL = 
            "CREATE TABLE IF NOT EXISTS playlist ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "ad_id TEXT NOT NULL, "
            "file_path TEXT NOT NULL, "
            "type TEXT, "
            "duration INTEGER, "
            "volume INTEGER, "
            "priority INTEGER, "
            "FOREIGN KEY(ad_id) REFERENCES advertisement(ad_id)"
            ");";
        db_->execute(createPlaylistTableSQL);

        std::cout << "数据库表结构初始化成功" << std::endl;
        return true;

    } catch (const std::exception& e) {
        std::cerr << "数据库初始化错误: " << e.what() << std::endl;
        return false;
    }
}

bool EdgeManager::syncAds() {
    try {
        std::ifstream f(config_.ads_config_path);
        if (!f.is_open()) {
            std::cerr << "无法打开广告配置文件: " << config_.ads_config_path << std::endl;
            return false;
        }

        json j;
        f >> j;

        return syncAds(j);

    } catch (const std::exception& e) {
        std::cerr << "加载广告数据失败: " << e.what() << std::endl;
        return false;
    }
}

bool EdgeManager::syncAds(const json& j) {
    try {
        if (!j.contains("ads")) {
            std::cerr << "Ads.json 格式错误: 缺少 'ads' 字段" << std::endl;
            return false;
        }

        auto ads = j["ads"].get<std::vector<Advertisement>>();
        std::cout << "读取到 " << ads.size() << " 条广告数据" << std::endl;

        // 开启事务
        db_->execute("BEGIN TRANSACTION;");

        for (const auto& ad : ads) {
            // 使用 REPLACE INTO 避免重复插入报错，且能更新数据
            // 注意：这里不再从 JSON 读取 last_played_time，而是保留数据库中原有的值（如果存在）或者设为 0
            std::string sql = "REPLACE INTO advertisement (ad_id, type, filename, md5, duration, bytes, last_played_time) VALUES ('"
                + ad.getAdId() + "', '"
                + ad.getType() + "', '"
                + ad.getFilename() + "', '"
                + ad.getMd5() + "', "
                + std::to_string(ad.getDuration()) + ", "
                + std::to_string(ad.getBytes()) + ", "
                + "0);"; // last_played_time 默认为 0
            db_->execute(sql);
        }

        db_->execute("COMMIT;");
        std::cout << "广告数据已入库" << std::endl;
        return true;

    } catch (const std::exception& e) {
        std::cerr << "解析广告数据异常: " << e.what() << std::endl;
        // 尝试回滚
        try { db_->execute("ROLLBACK;"); } catch (...) {}
        return false;
    }
}

bool EdgeManager::syncSchedule() {
    try {
        std::ifstream f(config_.schedule_config_path);
        if (!f.is_open()) {
            std::cerr << "无法打开排期配置文件: " << config_.schedule_config_path << std::endl;
            return false;
        }

        json j;
        f >> j;
        
        return syncSchedule(j);

    } catch (const std::exception& e) {
        std::cerr << "加载排期数据失败: " << e.what() << std::endl;
        return false;
    }
}

bool EdgeManager::syncSchedule(const json& j) {
    try {
        Schedule schedule = Schedule::fromJson(j);
        
        std::cout << "读取到排期策略: " << schedule.getPolicyId() << std::endl;

        db_->execute("BEGIN TRANSACTION;");

        // 1. 插入 schedule 表
        std::string scheduleSQL = "REPLACE INTO schedule (policy_id, effective_date, download_base_url, default_volume, download_retry_count, report_interval_sec) VALUES ('"
            + schedule.getPolicyId() + "', '"
            + schedule.getEffectiveDate() + "', '"
            + schedule.getDownloadBaseUrl() + "', "
            + std::to_string(schedule.getDefaultVolume()) + ", "
            + std::to_string(schedule.getDownloadRetryCount()) + ", "
            + std::to_string(schedule.getReportIntervalSec()) + ");";
        db_->execute(scheduleSQL);

        // 2. 插入 schedule_interrupt 表
        // 先删除旧的关联数据（简单起见，先删后插）
        db_->execute("DELETE FROM schedule_interrupt WHERE policy_id = '" + schedule.getPolicyId() + "';");
        for (const auto& interrupt : schedule.getInterrupts()) {
            std::string interruptSQL = "INSERT INTO schedule_interrupt (policy_id, trigger_type, ad_id, priority, play_mode, status) VALUES ('"
                + schedule.getPolicyId() + "', '"
                + interrupt.getTriggerType() + "', '"
                + interrupt.getAdId() + "', "
                + std::to_string(interrupt.getPriority()) + ", '"
                + interrupt.getPlayMode() + "', 0);"; // 默认 status = 0
            db_->execute(interruptSQL);
        }

        // 3. 插入 schedule_timeslot 表
        db_->execute("DELETE FROM schedule_timeslot WHERE policy_id = '" + schedule.getPolicyId() + "';");
        for (const auto& slot : schedule.getTimeSlots()) {
            // 将 playlist 数组转换为 JSON 字符串
            json playlistJson = slot.getPlaylist();
            std::string playlistStr = playlistJson.dump();

            std::string slotSQL = "INSERT INTO schedule_timeslot (policy_id, slot_id, time_range, volume, priority, loop_mode, playlist) VALUES ('"
                + schedule.getPolicyId() + "', "
                + std::to_string(slot.getSlotId()) + ", '"
                + slot.getTimeRange() + "', "
                + std::to_string(slot.getVolume()) + ", "
                + std::to_string(slot.getPriority()) + ", '"
                + slot.getLoopMode() + "', '"
                + playlistStr + "');";
            db_->execute(slotSQL);
        }

        db_->execute("COMMIT;");
        std::cout << "排期数据已入库" << std::endl;
        return true;

    } catch (const std::exception& e) {
        std::cerr << "解析排期数据异常: " << e.what() << std::endl;
        try { db_->execute("ROLLBACK;"); } catch (...) {}
        return false;
    }
}
