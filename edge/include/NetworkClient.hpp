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
     * @brief 启动网关连接 (WebSocket)
     * 
     * 负责建立长连接，并在一个连接中同时处理：
     * 1. 定时发送心跳 (10s)
     * 2. 定时上报日志 (30s)
     * 3. 接收服务端指令
     * 
     * @param wsUrl 网关 WebSocket 地址
     * @param deviceId 设备唯一标识符
     * @param token 认证 Token
     * @param logProvider 获取日志的回调函数 (返回 json 数组)
     * @param onSuccess 日志上报成功的回调函数 (参数为已上报的 log_id 列表)
     */
    void startGatewayConnection(const std::string& wsUrl, const std::string& deviceId, const std::string& token, 
                                std::function<json(int)> logProvider, 
                                std::function<void(const std::vector<std::string>&)> onSuccess,
                                std::function<void(const json&, std::function<void(const json&)>)> onMessage);

    /**
     * @brief 停止网关连接
     */
    void stopGatewayConnection();

    /**
     * @brief 从网关拉取最新广告素材数据
     * @return json 广告数据
     */
    json fetchAds();

    /**
     * @brief 从网关拉取最新排期策略数据
     * @return json 排期数据
     */
    json fetchSchedule();

    /**
     * @brief 向网关汇报同步结果
     * @param type 同步类型 ("ads" 或 "schedule")
     * @param status 状态 ("success" 或 "failed")
     * @param detail 详细信息
     * @return true 汇报成功
     */
    bool reportSyncResult(const std::string& type, const std::string& status, const std::string& detail);

private:
    std::string apiUrl_;

    std::thread wsThread_;
    std::atomic<bool> wsRunning_;
    std::atomic<void*> currentWs_{nullptr}; // 记录当前的 WebSocket 客户端指针，用于在外部关闭

    // WebSocket 网关维护循环
    void wsLoop(std::string wsUrl, std::string deviceId, std::string token,
                std::function<json(int)> logProvider, 
                std::function<void(const std::vector<std::string>&)> onSuccess,
                std::function<void(const json&, std::function<void(const json&)>)> onMessage);

    // 发送心跳
    bool sendHeartbeat(void* wsClient, const std::string& deviceId, const std::string& token);

    // 上报日志
    bool sendLogs(void* wsClient, std::function<json(int)> logProvider, 
                  std::function<void(const std::vector<std::string>&)> onSuccess);
};

#endif // NETWORK_CLIENT_HPP
