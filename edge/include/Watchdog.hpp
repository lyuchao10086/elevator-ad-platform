#ifndef WATCHDOG_HPP
#define WATCHDOG_HPP

#include <string>
#include <memory>
#include <thread>
#include <atomic>
#include <chrono>
#include <vector>
#include "Config.hpp"
#include "Database.hpp"
#include "NetworkClient.hpp"

/**
 * @class Watchdog
 * @brief 守护进程类，负责监控播放器进程状态、维持云端心跳及处理异常重启。
 */
class Watchdog {
public:
    Watchdog(const std::string& configPath, const std::string& exePath);
    ~Watchdog();

    /**
     * @brief 启动守护进程循环
     */
    void run();

private:
    std::string configPath_;
    std::string exePath_;
    Config config_;
    std::unique_ptr<Database> db_;
    std::unique_ptr<NetworkClient> network_;
    
    std::atomic<bool> should_exit_{false};
    pid_t player_pid_{-1};
    
    // 本地心跳监控
    std::atomic<long long> last_heartbeat_time_{0};
    
    // 核心逻辑
    void startPlayer();
    void stopPlayer();
    void monitorLoop();
    void cloudHeartbeatLoop();
    void localHeartbeatServer();
    
    // 故障记录
    void logFault(const std::string& type, const std::string& message);
    
    // 指令处理
    void handleCloudCommand(const json& msg, std::function<void(const json&)> send);
    
    // 辅助方法
    bool loadConfig();
    std::string generateUUID();
    long long getCurrentTimestamp();
};

#endif // WATCHDOG_HPP
