#ifndef PLAYITEM_HPP
#define PLAYITEM_HPP

#include <string>
#include <iostream>
#include "nlohmann/json.hpp"

using json = nlohmann::json;

/**
 * @brief 播放列表中的单项实体
 * 
 * 包含了播放器需要的所有信息，如文件路径、时长、音量等。
 * 这个对象通常是由 Scheduler 根据 Advertisement 和 Schedule 策略合并生成的。
 */
class PlayItem {
private:
    std::string ad_id;          // 广告ID (用于上报)
    std::string file_path;      // 媒体文件的绝对路径
    std::string type;           // 媒体类型 (video/image)
    int duration;               // 播放时长 (秒)
    int volume;                 // 播放音量 (0-100)
    int priority;               // 播放优先级

public:
    // 默认构造函数
    PlayItem() : duration(0), volume(0), priority(0) {}

    // 全参构造函数
    PlayItem(std::string id, std::string path, std::string t, int d, int v, int p)
        : ad_id(std::move(id)), file_path(std::move(path)), type(std::move(t)), 
          duration(d), volume(v), priority(p) {}

    // Getters
    std::string getAdId() const { return ad_id; }
    std::string getFilePath() const { return file_path; }
    std::string getType() const { return type; }
    int getDuration() const { return duration; }
    int getVolume() const { return volume; }
    int getPriority() const { return priority; }

    // Setters
    void setAdId(const std::string& id) { ad_id = id; }
    void setFilePath(const std::string& path) { file_path = path; }
    void setType(const std::string& t) { type = t; }
    void setDuration(int d) { duration = d; }
    void setVolume(int v) { volume = v; }
    void setPriority(int p) { priority = p; }

    /**
     * @brief 转换为字符串表示 (JSON 格式)
     */
    std::string toString() const {
        json j = *this;
        return j.dump(4);
    }

    /**
     * @brief 从 JSON 对象构造
     */
    static PlayItem fromJson(const json& j) {
        return j.get<PlayItem>();
    }

    /**
     * @brief 序列化为 JSON 对象
     */
    json toJson() const {
        return *this;
    }

    // nlohmann/json 宏，用于自动生成序列化/反序列化代码
    NLOHMANN_DEFINE_TYPE_INTRUSIVE(PlayItem, ad_id, file_path, type, duration, volume, priority)
};

#endif // PLAYITEM_HPP
