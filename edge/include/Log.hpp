#ifndef LOG_HPP
#define LOG_HPP

#include <string>
#include <nlohmann/json.hpp>

using json = nlohmann::json;

/**
 * @class Log
 * @brief 日志实体类
 */
class Log {
public:
    Log() : duration_ms(0), status_code(0), created_at(0), uploaded(0) {}
    
    // 完整的构造函数
    Log(std::string log_id, std::string device_id, std::string ad_id, std::string ad_file_name,
        std::string start_time, std::string end_time, int duration_ms, int status_code,
        std::string status_msg, long long created_at, std::string device_ip, std::string firmware_version, int uploaded = 0)
        : log_id(std::move(log_id)), device_id(std::move(device_id)), ad_id(std::move(ad_id)),
          ad_file_name(std::move(ad_file_name)), start_time(std::move(start_time)), end_time(std::move(end_time)),
          duration_ms(duration_ms), status_code(status_code), status_msg(std::move(status_msg)),
          created_at(created_at), device_ip(std::move(device_ip)), firmware_version(std::move(firmware_version)), uploaded(uploaded) {}

    // JSON 序列化
    NLOHMANN_DEFINE_TYPE_INTRUSIVE(Log, log_id, device_id, ad_id, ad_file_name, start_time, end_time, 
                                   duration_ms, status_code, status_msg, created_at, device_ip, firmware_version, uploaded)

private:
    std::string log_id;
    std::string device_id;
    std::string ad_id;
    std::string ad_file_name;
    std::string start_time;
    std::string end_time;
    int duration_ms;
    int status_code;
    std::string status_msg;
    long long created_at;
    std::string device_ip;
    std::string firmware_version;
    int uploaded; // 0: 未上传, 1: 已上传
};

#endif // LOG_HPP
