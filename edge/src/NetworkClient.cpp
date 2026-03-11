#include "NetworkClient.hpp"
#include "httplib.h"
#include <iostream>
#include <chrono>

NetworkClient::NetworkClient(const std::string& apiUrl) 
    : apiUrl_(apiUrl), running_(false), wsRunning_(false), port_(80) {
    parseUrl(apiUrl_, host_, port_, path_);
}

NetworkClient::~NetworkClient() {
    stop();
    stopGatewayConnection();
}

void NetworkClient::parseUrl(const std::string& url, std::string& host, int& port, std::string& path) {
    // 简单的 URL 解析 (http://host:port/path)
    // 默认值
    host = "127.0.0.1";
    port = 80;
    path = "/";

    std::string url_no_proto = url;
    if (url.find("http://") == 0) {
        url_no_proto = url.substr(7);
    } else if (url.find("https://") == 0) {
        // 暂不支持 https，按 http 处理
        url_no_proto = url.substr(8);
        port = 443;
    } else if (url.find("ws://") == 0) {
        url_no_proto = url.substr(5);
    } else if (url.find("wss://") == 0) {
         // 暂不支持 wss
        url_no_proto = url.substr(6);
        port = 443;
    }

    size_t portPos = url_no_proto.find(':');
    size_t pathPos = url_no_proto.find('/');
    
    if (portPos != std::string::npos) {
        host = url_no_proto.substr(0, portPos);
        if (pathPos != std::string::npos) {
            port = std::stoi(url_no_proto.substr(portPos + 1, pathPos - portPos - 1));
            path = url_no_proto.substr(pathPos);
        } else {
            port = std::stoi(url_no_proto.substr(portPos + 1));
            path = "/";
        }
    } else {
        if (pathPos != std::string::npos) {
            host = url_no_proto.substr(0, pathPos);
            path = url_no_proto.substr(pathPos);
        } else {
            host = url_no_proto;
            path = "/";
        }
    }
}

void NetworkClient::start(std::function<json(int)> logProvider, int intervalSec, const std::string& deviceId, const std::string& token, std::function<void(const std::vector<std::string>&)> onSuccess) {
    if (running_) return;
    
    running_ = true;
    workerThread_ = std::thread(&NetworkClient::workerLoop, this, logProvider, intervalSec, deviceId, token, onSuccess);
    std::cout << "[NetworkClient] 后台线程已启动 (" << host_ << ":" << port_ << ")" << std::endl;
}

void NetworkClient::stop() {
    if (running_) {
        running_ = false;
        if (workerThread_.joinable()) {
            workerThread_.join();
        }
        std::cout << "[NetworkClient] 后台线程已停止" << std::endl;
    }
}

bool NetworkClient::sendLogs(const json& logs) {
    if (logs.empty()) return true;

    httplib::Client cli(host_, port_);
    cli.set_connection_timeout(5); // 5秒连接超时

    auto res = cli.Post(path_.c_str(), logs.dump(), "application/json");
    
    if (res && res->status == 200) {
        return true;
    }
    
    std::cerr << "[NetworkClient] 发送失败: " << (res ? std::to_string(res->status) : "Connection Error") << std::endl;
    return false;
}

void NetworkClient::workerLoop(std::function<json(int)> logProvider, int intervalSec, const std::string& deviceId, const std::string& token, std::function<void(const std::vector<std::string>&)> onSuccess) {
    bool useWs = (apiUrl_.find("ws://") == 0 || apiUrl_.find("wss://") == 0);

    if (useWs) {
        // WebSocket 模式
        // 适用于需要高频、低延迟日志上报的场景
        while (running_) {
            std::cout << "[NetworkClient] 正在连接日志服务器: " << apiUrl_ << " ..." << std::endl;
            try {
                // 使用完整 URL 构造 (不需要拼参数，参数在 body 里)
                httplib::ws::WebSocketClient ws(apiUrl_);
                
                // 设置读超时 (非阻塞读)
                // 允许我们在没有收到服务器消息时也能定期检查是否有日志需要发送
                // ws.set_read_timeout(1, 0); // 移除超时设置，避免read超时导致连接断开

                if (ws.connect()) {
                    std::cout << "[NetworkClient] 日志 WebSocket 连接成功" << std::endl;
                    
                    while (running_) {
                        // 1. 获取并发送日志
                        // 定期查询数据库中未上传的日志
                        try {
                            json logs = logProvider(50);
                            if (!logs.empty()) {
                                // 构造日志包
                                // 封装日志格式: {id:xxx, token:xxx, logs:xxx}
                                json payload;
                                payload["id"] = deviceId;
                                payload["token"] = token;
                                payload["logs"] = logs;
                                
                                if (!ws.send(payload.dump())) {
                                    std::cerr << "[NetworkClient] 日志发送失败 (WS)" << std::endl;
                                    break; // 发送失败通常意味着连接断开，跳出循环触发重连
                                }
                                // std::cout << "[NetworkClient] 日志上报成功 (WS): " << logs.size() << " 条" << std::endl;
                                
                                // 回调通知上报成功
                                if (onSuccess) {
                                    std::vector<std::string> logIds;
                                    for (const auto& log : logs) {
                                        if (log.contains("log_id")) {
                                            logIds.push_back(log["log_id"]);
                                        }
                                    }
                                    if (!logIds.empty()) {
                                        onSuccess(logIds);
                                    }
                                }
                            }
                        } catch (const std::exception& e) {
                            std::cerr << "[NetworkClient] 获取日志异常: " << e.what() << std::endl;
                        }

                        // 2. 等待间隔 (期间处理底层 IO，如 PING)
                        // 分段休眠并读取，确保能及时响应停止信号，并维持 WebSocket 连接活性
                        for (int i = 0; i < intervalSec; ++i) {
                            if (!running_) break;
                            std::this_thread::sleep_for(std::chrono::seconds(1));
                            
                            // 移除主动 read，避免超时导致连接断开
                            // 如果服务器不主动发消息，read 会一直超时
                            // std::string msg;
                            // auto res = ws.read(msg);
                            
                            // 检查连接是否断开 (简单检查)
                            // if (!ws.is_open()) { ... }
                        }
                        
                        // 如果连接已关闭，跳出循环
                        // 注意：如果不调用 read，httplib 可能不会及时更新 is_open 状态，直到 send 失败
                        // 这是可以接受的
                    }
                } else {
                    std::cerr << "[NetworkClient] 日志 WebSocket 连接失败" << std::endl;
                }
            } catch (const std::exception& e) {
                std::cerr << "[NetworkClient] 日志 WS 异常: " << e.what() << std::endl;
            }

            if (running_) {
                std::cout << "[NetworkClient] 日志 WS 5秒后重连..." << std::endl;
                std::this_thread::sleep_for(std::chrono::seconds(5));
            }
        }
    } else {
        // HTTP 模式 (原有逻辑)
        while (running_) {
            // 等待间隔
            for (int i = 0; i < intervalSec; ++i) {
                if (!running_) return;
                std::this_thread::sleep_for(std::chrono::seconds(1));
            }

            try {
                // 获取日志 (每次 50 条)
                json logs = logProvider(50);
                
                if (!logs.empty()) {
                    if (sendLogs(logs)) {
                        // std::cout << "[NetworkClient] 日志上报成功: " << logs.size() << " 条" << std::endl;
                        
                        // 回调通知上报成功
                        if (onSuccess) {
                            std::vector<std::string> logIds;
                            for (const auto& log : logs) {
                                if (log.contains("log_id")) {
                                    logIds.push_back(log["log_id"]);
                                }
                            }
                            if (!logIds.empty()) {
                                onSuccess(logIds);
                            }
                        }
                    }
                }
            } catch (const std::exception& e) {
                std::cerr << "[NetworkClient] 异常: " << e.what() << std::endl;
            }
        }
    }
}

void NetworkClient::startGatewayConnection(const std::string& wsUrl, const std::string& deviceId, const std::string& token) {
    if (wsRunning_) return;
    
    wsRunning_ = true;
    wsThread_ = std::thread(&NetworkClient::wsLoop, this, wsUrl, deviceId, token);
    std::cout << "[NetworkClient] 网关连接线程已启动 (URL: " << wsUrl << ")" << std::endl;
}

void NetworkClient::stopGatewayConnection() {
    if (wsRunning_) {
        wsRunning_ = false;
        if (wsThread_.joinable()) {
            wsThread_.join();
        }
        std::cout << "[NetworkClient] 网关连接线程已停止" << std::endl;
    }
}

void NetworkClient::wsLoop(std::string wsUrl, std::string deviceId, std::string token) {
    while (wsRunning_) {
        // 1. 构造完整 URL (带鉴权参数)
        // 简单判断是否已有 query
        std::string fullUrl = wsUrl;
        if (fullUrl.find('?') == std::string::npos) {
            fullUrl += "?device_id=" + deviceId + "&token=" + token;
        } else {
            fullUrl += "&device_id=" + deviceId + "&token=" + token;
        }

        std::cout << "[NetworkClient] 正在连接网关: " << wsUrl << " ..." << std::endl;

        try {
            // 创建 WebSocket 客户端
            httplib::ws::WebSocketClient ws(fullUrl);
            
            // 设置超时
            // ws.set_connection_timeout(5, 0); // WebSocketClient 没有此方法
            // ws.set_read_timeout(1, 0);       // 移除读超时，改为阻塞读，避免超时导致连接断开
            
            if (ws.connect()) {
                std::cout << "[NetworkClient] 网关 WebSocket 连接成功!" << std::endl;
                
                // 启动心跳发送线程
                // 独立线程负责定期发送 PING 或自定义心跳包，保持连接活跃
                std::atomic<bool> hbRunning(true);
                int heartbeatIntervalSec = 5;
                std::thread hbThread([&, heartbeatIntervalSec]() {
                    while (hbRunning && wsRunning_) {
                        // 发送心跳
                        json heartbeat;
                        heartbeat["id"] = deviceId;
                        heartbeat["token"] = token;

                        // 注意：httplib 的 send 在多线程下可能需要注意，但通常 socket 读写分离是安全的
                        if (ws.send(heartbeat.dump())) {
                            std::cout << "[NetworkClient] WebSocket 心跳发送成功" << std::endl;
                        } else {
                            std::cerr << "[NetworkClient] WebSocket 心跳发送失败" << std::endl;
                            break;
                        }

                        // 等待间隔
                        for (int i = 0; i < heartbeatIntervalSec; ++i) {
                            if (!hbRunning || !wsRunning_) break;
                            std::this_thread::sleep_for(std::chrono::seconds(1));
                        }
                    }
                });

                while (wsRunning_) {
                    // 阻塞读取消息
                    // 等待服务端下发的指令 (如更新排期、重启设备等)
                    std::string msg;
                    auto res = ws.read(msg);
                    
                    if (res == httplib::ws::ReadResult::Text || res == httplib::ws::ReadResult::Binary) {
                        // 收到消息
                        std::cout << "[NetworkClient] 收到网关消息: " << msg << std::endl;
                        // TODO: 处理业务消息 (这里需要一个回调机制将消息传递给 EdgeManager)
                        
                    } else {
                        // 连接关闭或错误
                        std::cerr << "[NetworkClient] WebSocket 连接已关闭或发生错误" << std::endl;
                        break; // 退出循环，触发重连
                    }
                }

                // 清理心跳线程
                hbRunning = false;
                if (hbThread.joinable()) {
                    hbThread.join();
                }
            } else {
                std::cerr << "[NetworkClient] WebSocket 连接失败" << std::endl;
            }

        } catch (const std::exception& e) {
            std::cerr << "[NetworkClient] WebSocket 异常: " << e.what() << std::endl;
        }

        // 重连等待
        if (wsRunning_) {
            std::cout << "[NetworkClient] 5秒后尝试重连..." << std::endl;
            std::this_thread::sleep_for(std::chrono::seconds(5));
        }
    }
}
