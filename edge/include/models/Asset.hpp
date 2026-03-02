#ifndef ASSET_HPP
#define ASSET_HPP

#include <string>
#include <vector>
#include "nlohmann/json.hpp"

using json = nlohmann::json;

/**
 * @brief 广告类
 * 
 * 对应 Assets.json 中的 assets 数组中的单项
 */
class Asset {
public:
    Asset();
    
    /**
     * @brief 全参构造函数
     * @param id 广告 ID
     * @param type 广告类型
     * @param filename 文件名
     * @param md5 文件 MD5
     * @param duration 时长
     * @param bytes 文件大小
     */
    Asset(const std::string& id, const std::string& type, const std::string& filename, 
          const std::string& md5, int duration, long long bytes, long long lastPlayedTime = 0);

    /**
     * @brief 构造函数：从 JSON 对象构造
     * @param j nlohmann::json 对象
     */
    explicit Asset(const json& j);

    // Getters
    std::string getId() const;
    std::string getType() const;
    std::string getFilename() const;
    std::string getMd5() const;
    int getDuration() const;
    long long getBytes() const;
    long long getLastPlayedTime() const;

    // Setters
    void setId(const std::string& id);
    void setType(const std::string& type);
    void setFilename(const std::string& filename);
    void setMd5(const std::string& md5);
    void setDuration(int duration);
    void setBytes(long long bytes);
    void setLastPlayedTime(long long lastPlayedTime);

    /**
     * @brief 序列化为 JSON 对象
     * @return nlohmann::json
     */
    json toJson() const;

    /**
     * @brief 序列化为 JSON 字符串
     * @return std::string
     */
    std::string toString() const;

private:
    std::string id_;
    std::string type_;
    std::string filename_;
    std::string md5_;
    int duration_;
    long long bytes_;
    long long lastPlayedTime_;
};

// nlohmann/json 序列化/反序列化辅助函数
void to_json(json& j, const Asset& p);
void from_json(const json& j, Asset& p);

#endif // ASSET_HPP
