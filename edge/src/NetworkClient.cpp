#include "NetworkClient.hpp"
#include "httplib.h"
#include <iostream>
#include <chrono>

NetworkClient::NetworkClient(const std::string& apiUrl, const std::string& deviceId, const std::string& token) 
    : apiUrl_(apiUrl), deviceId_(deviceId), token_(token), wsRunning_(false) {
}

NetworkClient::~NetworkClient() {
    stopGatewayConnection();
}

void NetworkClient::startGatewayConnection(const std::string& wsUrl, const std::string& deviceId, const std::string& token, 
                                           std::function<json(int)> logProvider, 
                                           std::function<void(const std::vector<std::string>&)> onSuccess,
                                           std::function<void(const json&, std::function<void(const json&)>)> onMessage) {
    if (wsRunning_) return;
    
    wsRunning_ = true;
    wsThread_ = std::thread(&NetworkClient::wsLoop, this, wsUrl, deviceId, token, logProvider, onSuccess, onMessage);
    std::cout << "[NetworkClient] 网关连接线程已启动 (URL: " << wsUrl << ")" << std::endl;
}

void NetworkClient::stopGatewayConnection() {
    if (wsRunning_) {
        wsRunning_ = false;
        
        // 如果当前有正在连接的 WebSocket，主动关闭它以打断阻塞的 read()
        void* ptr = currentWs_.load();
        if (ptr) {
            auto* ws = static_cast<httplib::ws::WebSocketClient*>(ptr);
            try {
                ws->close();
            } catch (...) {}
        }

        if (wsThread_.joinable()) {
            wsThread_.join();
        }
        std::cout << "[NetworkClient] 网关连接线程已停止" << std::endl;
    }
}

void NetworkClient::wsLoop(std::string wsUrl, std::string deviceId, std::string token,
                           std::function<json(int)> logProvider, 
                           std::function<void(const std::vector<std::string>&)> onSuccess,
                           std::function<void(const json&, std::function<void(const json&)>)> onMessage) {
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
            currentWs_ = &ws; // 记录当前活跃的客户端
            
            if (ws.connect()) {
                std::cout << "[NetworkClient] 网关 WebSocket 连接成功!" << std::endl;
                
                // 启动后台任务线程 (负责定时发送心跳和日志)
                // 独立线程负责发送，保持连接活跃，且不阻塞主读取循环
                std::atomic<bool> senderRunning(true);
                
                std::thread senderThread([&]() {
                    int heartbeatCounter = 0;
                    int logReportCounter = 0;
                    const int baseInterval = 1; // 基础刻度 1秒

                    while (senderRunning && wsRunning_) {
                        std::this_thread::sleep_for(std::chrono::seconds(baseInterval));
                        if (!senderRunning || !wsRunning_) break;

                        heartbeatCounter += baseInterval;
                        logReportCounter += baseInterval;

                        // --- 1. 发送心跳 (10s) ---
                        if (heartbeatCounter >= 10) {
                            heartbeatCounter = 0;
                            if (!this->sendHeartbeat(&ws, deviceId, token)) {
                                break; // 发送失败，退出循环，触发断开重连
                            }
                        }

                        // --- 2. 上报日志 (30s) ---
                        if (logReportCounter >= 30) {
                            logReportCounter = 0;
                            if (!this->sendLogs(&ws, logProvider, onSuccess)) {
                                break; // 发送失败，退出
                            }
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
                        try {
                            json j = json::parse(msg);
                            if (onMessage) {
                                auto sendFunc = [&](const json& reply){
                                    ws.send(reply.dump());
                                };
                                onMessage(j, sendFunc);
                            }
                        } catch (const std::exception& e) {
                            std::cerr << "[NetworkClient] 解析消息失败: " << e.what() << std::endl;
                        }
                        
                    } else {
                        // 连接关闭或错误
                        std::cerr << "[NetworkClient] WebSocket 连接已关闭或发生错误" << std::endl;
                        break; // 退出循环，触发重连
                    }
                }

                // 清理发送线程
                senderRunning = false;
                if (senderThread.joinable()) {
                    senderThread.join();
                }
            } else {
                std::cerr << "[NetworkClient] WebSocket 连接失败" << std::endl;
            }
            currentWs_ = nullptr; // 连接关闭后清除记录
        } catch (const std::exception& e) {
            currentWs_ = nullptr;
            std::cerr << "[NetworkClient] WebSocket 异常: " << e.what() << std::endl;
        }

        // 重连等待
        if (wsRunning_) {
            std::cout << "[NetworkClient] 5秒后尝试重连..." << std::endl;
            // 分段休眠，以便快速响应停止信号
            for (int i = 0; i < 50 && wsRunning_; ++i) {
                std::this_thread::sleep_for(std::chrono::milliseconds(100));
            }
        }
    }
}

json NetworkClient::fetchAds() {
    try {
        httplib::Client cli(apiUrl_);
        std::string path = "/api/ads";
        if (!deviceId_.empty()) {
            path += (path.find('?') == std::string::npos ? "?" : "&");
            path += "device_id=" + deviceId_ + "&token=" + token_;
        }
        
        auto res = cli.Get(path.c_str()); 
        if (res && res->status == 200) {
            std::cout << "[NetworkClient] 获取广告数据成功" << std::endl;
            return json::parse(res->body);
        } else {
            std::cerr << "[NetworkClient] 获取广告数据失败: " << (res ? std::to_string(res->status) : "无法连接") << std::endl;
        }
    } catch (const std::exception& e) {
        std::cerr << "[NetworkClient] 获取广告数据异常: " << e.what() << std::endl;
    }
    return json::object();
}

json NetworkClient::fetchSchedule() {
    try {
        httplib::Client cli(apiUrl_);
        std::string path = "/api/schedule";
        if (!deviceId_.empty()) {
            path += (path.find('?') == std::string::npos ? "?" : "&");
            path += "device_id=" + deviceId_ + "&token=" + token_;
        }
        
        auto res = cli.Get(path.c_str()); 
        if (res && res->status == 200) {
            std::cout << "[NetworkClient] 获取排期数据成功" << std::endl;
            return json::parse(res->body);
        } else {
            std::cerr << "[NetworkClient] 获取排期数据失败: " << (res ? std::to_string(res->status) : "无法连接") << std::endl;
        }
    } catch (const std::exception& e) {
        std::cerr << "[NetworkClient] 获取排期数据异常: " << e.what() << std::endl;
    }
    return json::object();
}

bool NetworkClient::reportSyncResult(const std::string& type, const std::string& status, const std::string& detail) {
    try {
        httplib::Client cli(apiUrl_);
        json payload;
        payload["device_id"] = deviceId_;
        payload["type"] = type;
        payload["status"] = status;
        payload["detail"] = detail;
        payload["timestamp"] = std::time(nullptr);

        std::string path = "/api/sync/report";
        if (!token_.empty()) {
            path += "?token=" + token_;
        }

        auto res = cli.Post(path.c_str(), payload.dump(), "application/json");
        if (res && res->status == 200) {
            std::cout << "[NetworkClient] 同步结果汇报成功: " << type << " - " << status << std::endl;
            return true;
        } else {
            std::cerr << "[NetworkClient] 同步结果汇报失败: " << (res ? std::to_string(res->status) : "无法连接") << std::endl;
        }
    } catch (const std::exception& e) {
        std::cerr << "[NetworkClient] 同步结果汇报异常: " << e.what() << std::endl;
    }
    return false;
}

bool NetworkClient::sendHeartbeat(void* wsClient, const std::string& deviceId, const std::string& token) {
    if (!wsClient) return false;
    auto* ws = static_cast<httplib::ws::WebSocketClient*>(wsClient);

    json heartbeat;
    heartbeat["type"] = "heartbeat";
    heartbeat["payload"] = "ping";
    
    if (ws->send(heartbeat.dump())) {
        std::cout << "[NetworkClient] WebSocket 心跳发送成功" << std::endl;
        return true;
    } else {
        std::cerr << "[NetworkClient] WebSocket 心跳发送失败" << std::endl;
        return false;
    }
}

bool NetworkClient::sendLogs(void* wsClient, std::function<json(int)> logProvider, 
                             std::function<void(const std::vector<std::string>&)> onSuccess) {
    if (!wsClient) return false;
    auto* ws = static_cast<httplib::ws::WebSocketClient*>(wsClient);

    try {
        json logs = logProvider(50); // 每次最多50条
        if (!logs.empty()) {
            json payload;
            payload["type"] = "log";
            payload["payload"] = logs;
            
            if (ws->send(payload.dump())) {
                std::cout << "[NetworkClient] 日志上报成功: " << logs.size() << " 条" << std::endl;
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
                return true;
            } else {
                std::cerr << "[NetworkClient] 日志发送失败" << std::endl;
                return false;
            }
        }
        return true; // 没有日志也算成功
    } catch (const std::exception& e) {
        std::cerr << "[NetworkClient] 获取/发送日志异常: " << e.what() << std::endl;
        return false;
    }
}
