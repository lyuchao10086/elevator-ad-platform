#ifndef SCHEDULE_HPP
#define SCHEDULE_HPP

#include <string>
#include <vector>
#include "nlohmann/json.hpp"

using json = nlohmann::json;

/**
 * @brief 插播广告策略
 */
class Interrupt {
private:
    std::string trigger_type;
    std::string ad_id;
    int priority;
    std::string play_mode;

public:
    Interrupt() : priority(0) {}

    // Getters
    std::string getTriggerType() const { return trigger_type; }
    std::string getAdId() const { return ad_id; }
    int getPriority() const { return priority; }
    std::string getPlayMode() const { return play_mode; }

    // Setters
    void setTriggerType(const std::string& type) { trigger_type = type; }
    void setAdId(const std::string& id) { ad_id = id; }
    void setPriority(int p) { priority = p; }
    void setPlayMode(const std::string& mode) { play_mode = mode; }

    std::string toString() const {
        json j = *this;
        return j.dump(4);
    }

    NLOHMANN_DEFINE_TYPE_INTRUSIVE(Interrupt, trigger_type, ad_id, priority, play_mode)
};

/**
 * @brief 时间段播放策略
 */
class TimeSlot {
private:
    int slot_id;
    std::string time_range;
    int volume;
    int priority;
    std::string loop_mode;
    std::vector<std::string> playlist;

public:
    TimeSlot() : slot_id(0), volume(0), priority(0) {}

    // Getters
    int getSlotId() const { return slot_id; }
    std::string getTimeRange() const { return time_range; }
    int getVolume() const { return volume; }
    int getPriority() const { return priority; }
    std::string getLoopMode() const { return loop_mode; }
    std::vector<std::string> getPlaylist() const { return playlist; }

    // Setters
    void setSlotId(int id) { slot_id = id; }
    void setTimeRange(const std::string& range) { time_range = range; }
    void setVolume(int v) { volume = v; }
    void setPriority(int p) { priority = p; }
    void setLoopMode(const std::string& mode) { loop_mode = mode; }
    void setPlaylist(const std::vector<std::string>& list) { playlist = list; }

    std::string toString() const {
        json j = *this;
        return j.dump(4);
    }

    NLOHMANN_DEFINE_TYPE_INTRUSIVE(TimeSlot, slot_id, time_range, volume, priority, loop_mode, playlist)
};

/**
 * @brief 整体排期策略
 */
class Schedule {
private:
    std::string policy_id;
    std::string effective_date;
    std::string download_base_url;
    int default_volume;
    int download_retry_count;
    int report_interval_sec;
    std::vector<Interrupt> interrupts;
    std::vector<TimeSlot> time_slots;

public:
    Schedule() : default_volume(0), download_retry_count(0), report_interval_sec(0) {}

    // Getters
    std::string getPolicyId() const { return policy_id; }
    std::string getEffectiveDate() const { return effective_date; }
    std::string getDownloadBaseUrl() const { return download_base_url; }
    int getDefaultVolume() const { return default_volume; }
    int getDownloadRetryCount() const { return download_retry_count; }
    int getReportIntervalSec() const { return report_interval_sec; }
    const std::vector<Interrupt>& getInterrupts() const { return interrupts; }
    const std::vector<TimeSlot>& getTimeSlots() const { return time_slots; }

    // Setters
    void setPolicyId(const std::string& id) { policy_id = id; }
    void setEffectiveDate(const std::string& date) { effective_date = date; }
    void setDownloadBaseUrl(const std::string& url) { download_base_url = url; }
    void setDefaultVolume(int v) { default_volume = v; }
    void setDownloadRetryCount(int c) { download_retry_count = c; }
    void setReportIntervalSec(int sec) { report_interval_sec = sec; }
    void setInterrupts(const std::vector<Interrupt>& list) { interrupts = list; }
    void setTimeSlots(const std::vector<TimeSlot>& list) { time_slots = list; }

    std::string toString() const {
        json j = *this;
        return j.dump(4);
    }

    static Schedule fromJson(const json& j) {
        return j.get<Schedule>();
    }

    json toJson() const {
        return *this;
    }

    NLOHMANN_DEFINE_TYPE_INTRUSIVE(Schedule, policy_id, effective_date, download_base_url, default_volume, 
                                   download_retry_count, report_interval_sec, interrupts, time_slots)
};

#endif // SCHEDULE_HPP
