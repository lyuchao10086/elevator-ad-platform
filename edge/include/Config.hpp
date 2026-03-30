#ifndef CONFIG_HPP
#define CONFIG_HPP

#include <string>
#include "nlohmann/json.hpp"

// --- 系统级常量 ---
const int WD_HEARTBEAT_PORT = 9999;     // 守护进程心跳接收端口 (UDP)
const int WD_COMMAND_PORT = 9998;       // 播放器命令接收端口 (UDP)
const std::string WD_LOCALHOST = "127.0.0.1";

using json = nlohmann::json;

/**
 * @brief 运行时全局配置参数
 */
struct Config {
    std::string db_path;            // 数据库文件路径 (e.g., "resources/edge.db")
    std::string resources_dir;      // 资源文件根目录 (e.g., "resources/")
    std::string ads_config_path;    // 广告素材配置文件路径 (e.g., "resources/Ads.json")
    std::string schedule_config_path; // 排期策略配置文件路径 (e.g., "resources/Schedule.json")
    std::string gateway_ws_url;     // 网关 WebSocket 地址 (e.g. ws://10.12.58.85:8080/ws)
    std::string device_id;          // 设备唯一标识符
    std::string token;              // 认证 Token
    int log_level;                  // 日志级别 (0: DEBUG, 1: INFO, 2: WARN, 3: ERROR)

    Config() : log_level(1) {}

    // 支持 JSON 序列化/反序列化
    NLOHMANN_DEFINE_TYPE_INTRUSIVE(Config, db_path, resources_dir, ads_config_path, schedule_config_path, gateway_ws_url, device_id, token, log_level)
};

#endif // CONFIG_HPP
