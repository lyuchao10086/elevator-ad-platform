#ifndef INTERRUPT_HPP
#define INTERRUPT_HPP

#include <string>
#include "nlohmann/json.hpp"

using json = nlohmann::json;

/**
 * @brief 插播广告配置类
 * 
 * 定义了插播广告的触发条件和播放属性
 */
class Interrupt {
public:
    Interrupt();
    /**
     * @brief 全参构造函数
     * @param triggerType 触发类型
     * @param adId 广告 ID
     * @param priority 优先级
     * @param playMode 播放模式
     */
    Interrupt(const std::string& triggerType, const std::string& adId, int priority, const std::string& playMode);
    explicit Interrupt(const json& j);

    // Getters
    std::string getTriggerType() const;
    std::string getAdId() const;
    int getPriority() const;
    std::string getPlayMode() const;

    // Setters
    void setTriggerType(const std::string& triggerType);
    void setAdId(const std::string& adId);
    void setPriority(int priority);
    void setPlayMode(const std::string& playMode);

    json toJson() const;
    std::string toString() const;

private:
    std::string trigger_type_;
    std::string ad_id_;
    int priority_;
    std::string play_mode_;
};

// nlohmann/json 辅助函数
void to_json(json& j, const Interrupt& p);
void from_json(const json& j, Interrupt& p);

#endif // INTERRUPT_HPP
