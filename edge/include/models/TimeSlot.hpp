#ifndef TIMESLOT_HPP
#define TIMESLOT_HPP

#include <string>
#include <vector>
#include "nlohmann/json.hpp"

using json = nlohmann::json;

/**
 * @brief 时间段播放配置类
 * 
 * 定义了特定时间段内的播放列表和属性
 */
class TimeSlot {
public:
    TimeSlot();
    /**
     * @brief 全参构造函数
     * @param slotId 时间段 ID
     * @param timeRange 时间范围
     * @param volume 音量
     * @param priority 优先级
     * @param loopMode 循环模式
     * @param playlist 播放列表
     */
    TimeSlot(int slotId, const std::string& timeRange, int volume, int priority, 
             const std::string& loopMode, const std::vector<std::string>& playlist);
    explicit TimeSlot(const json& j);

    // Getters
    int getSlotId() const;
    std::string getTimeRange() const;
    int getVolume() const;
    int getPriority() const;
    std::string getLoopMode() const;
    const std::vector<std::string>& getPlaylist() const;

    // Setters
    void setSlotId(int slotId);
    void setTimeRange(const std::string& timeRange);
    void setVolume(int volume);
    void setPriority(int priority);
    void setLoopMode(const std::string& loopMode);
    void setPlaylist(const std::vector<std::string>& playlist);
    void addPlaylistItem(const std::string& item);

    json toJson() const;
    std::string toString() const;

private:
    int slot_id_;
    std::string time_range_;
    int volume_;
    int priority_;
    std::string loop_mode_;
    std::vector<std::string> playlist_;
};

// nlohmann/json 辅助函数
void to_json(json& j, const TimeSlot& p);
void from_json(const json& j, TimeSlot& p);

#endif // TIMESLOT_HPP
