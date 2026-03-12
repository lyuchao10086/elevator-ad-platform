#include "NetworkClient.hpp"
#include "httplib.h"
#include <iostream>
#include <chrono>

NetworkClient::NetworkClient(const std::string& apiUrl) 
    : apiUrl_(apiUrl), wsRunning_(false) {
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
