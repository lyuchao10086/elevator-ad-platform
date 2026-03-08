#ifndef NETWORK_CLIENT_HPP
#define NETWORK_CLIENT_HPP

#include <string>
#include <vector>
#include <thread>
#include <atomic>
#include <functional>
#include <nlohmann/json.hpp>

using json = nlohmann::json;

/**
 * @class NetworkClient
 * @brief 网络通信客户端
 * 
 * 负责与云端/网关进行 HTTP 通信，包括日志上报、心跳维护等。
 * 封装了 httplib 和后台发送线程。
 */
class NetworkClient {
public:
    /**
     * @brief 构造函数
     * @param apiUrl 云端 API 基础地址 (例如 http://127.0.0.1:8080/api)
     */
    explicit NetworkClient(const std::string& apiUrl);

    ~NetworkClient();

    /**
     * @brief 启动后台任务 (如定期日志上报)
     * 
     * @param logProvider 获取日志的回调函数 (返回 json 数组)
     * @param intervalSec 上报间隔 (秒)
     * @param deviceId 设备 ID
     * @param token 设备 Token
     * @param onSuccess 上报成功的回调函数 (参数为已上报的 log_id 列表)
     */
    void start(std::function<json(int)> logProvider, int intervalSec, const std::string& deviceId, const std::string& token, std::function<void(const std::vector<std::string>&)> onSuccess = nullptr);

    /**
     * @brief 停止后台任务
     */
    void stop();

    /**
     * @brief 发送日志 (单次调用)
     * @param logs 日志数据
     * @return true 发送成功
     */
    bool sendLogs(const json& logs);

    /**
     * @brief 启动网关连接 (WebSocket)
     * 
     * @param wsUrl 网关 WebSocket 地址
     * @param deviceId 设备唯一标识符
     * @param token 认证 Token
     */
    void startGatewayConnection(const std::string& wsUrl, const std::string& deviceId, const std::string& token);

    /**
     * @brief 停止网关连接
     */
    void stopGatewayConnection();

private:
    std::string apiUrl_;
    std::string host_;
    int port_;
    std::string path_;

    std::thread workerThread_;
    std::atomic<bool> running_;

    std::thread wsThread_;
    std::atomic<bool> wsRunning_;

    // 解析 URL
    void parseUrl(const std::string& url, std::string& host, int& port, std::string& path);

    // 工作线程循环 (负责日志上报)
    void workerLoop(std::function<json(int)> logProvider, int intervalSec, const std::string& deviceId, const std::string& token, std::function<void(const std::vector<std::string>&)> onSuccess);
    
    // WebSocket 网关维护循环 (负责接收指令和心跳)
    void wsLoop(std::string wsUrl, std::string deviceId, std::string token);

    // --- 内部封装方法 ---

    // [日志上报] 发送日志数据包 (WS)
    bool sendLogPacket(void* wsClient, const json& logs, const std::string& deviceId, const std::string& token);

    // [网关] 心跳发送循环
    void gatewayHeartbeatLoop(void* wsClient, const std::string& deviceId, const std::string& token, std::atomic<bool>& hbRunning);

    // [网关] 消息接收循环
    void gatewayReceiveLoop(void* wsClient);
};

#endif // NETWORK_CLIENT_HPP
