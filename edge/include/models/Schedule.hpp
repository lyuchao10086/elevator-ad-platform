#ifndef SCHEDULE_HPP
#define SCHEDULE_HPP

#include <string>
#include <vector>
#include "nlohmann/json.hpp"
#include "models/Interrupt.hpp"
#include "models/TimeSlot.hpp"

using json = nlohmann::json;

/**
 * @brief 日程策略类
 * 
 * 对应 Schedule.json 的根对象，包含全局策略配置、插播配置和时间段列表
 */
class Schedule {
public:
    Schedule();
    /**
     * @brief 全参构造函数
     * @param policyId 策略 ID
     * @param effectiveDate 生效日期
     * @param downloadBaseUrl 下载基准 URL
     * @param defaultVolume 默认音量
     * @param downloadRetryCount 下载重试次数
     * @param reportIntervalSec 上报间隔
     * @param interrupts 插播广告配置
     * @param timeSlots 时间段列表
     */
    Schedule(const std::string& policyId, const std::string& effectiveDate, const std::string& downloadBaseUrl,
             int defaultVolume, int downloadRetryCount, int reportIntervalSec,
             const Interrupt& interrupts, const std::vector<TimeSlot>& timeSlots);
    explicit Schedule(const json& j);

    // Getters
    std::string getPolicyId() const;
    std::string getEffectiveDate() const;
    std::string getDownloadBaseUrl() const;
    int getDefaultVolume() const;
    int getDownloadRetryCount() const;
    int getReportIntervalSec() const;
    Interrupt getInterrupts() const;
    const std::vector<TimeSlot>& getTimeSlots() const;

    // Setters
    void setPolicyId(const std::string& policyId);
    void setEffectiveDate(const std::string& effectiveDate);
    void setDownloadBaseUrl(const std::string& url);
    void setDefaultVolume(int volume);
    void setDownloadRetryCount(int count);
    void setReportIntervalSec(int interval);
    void setInterrupts(const Interrupt& interrupts);
    void setTimeSlots(const std::vector<TimeSlot>& timeSlots);
    void addTimeSlot(const TimeSlot& slot);

    json toJson() const;
    std::string toString() const;

private:
    std::string policy_id_;
    std::string effective_date_;
    std::string download_base_url_;
    int default_volume_;
    int download_retry_count_;
    int report_interval_sec_;
    Interrupt interrupts_;
    std::vector<TimeSlot> time_slots_;
};

// nlohmann/json 辅助函数
void to_json(json& j, const Schedule& p);
void from_json(const json& j, Schedule& p);

#endif // SCHEDULE_HPP
