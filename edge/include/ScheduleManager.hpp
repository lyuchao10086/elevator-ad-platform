#ifndef SCHEDULE_MANAGER_HPP
#define SCHEDULE_MANAGER_HPP

#include "Database.hpp"
#include "models/Asset.hpp"
#include "models/Schedule.hpp"
#include "models/Interrupt.hpp"
#include "models/TimeSlot.hpp"
#include "models/PlayItem.hpp"
#include <optional>
#include <map>
#include <mutex>
#include <vector>

class ScheduleManager {
public:
    explicit ScheduleManager(const std::string& dbPath);

    void initSchema();
    void clearAll();
    
    // 清空播放队列 (DB)
    void clearPlayQueue();

    void insertAsset(const Asset& asset);
    std::optional<Asset> getAsset(const std::string& id) const;
    void updateAsset(const Asset& asset);
    void deleteAsset(const std::string& id);

    void insertSchedule(const Schedule& schedule);
    std::optional<Schedule> getSchedule(const std::string& policyId);
    void updateSchedule(const Schedule& schedule);
    void deleteSchedule(const std::string& policyId);

    // 从 JSON 字符串加载日程 (云端格式)
    void syncSchedule(const std::string& jsonStr);

    // 触发插播
    bool triggerInterrupt(const Interrupt& interrupt);

    // 获取当前播放队列
    std::vector<PlayItem> getPlayQueue() const;

    // 清空并重新生成播放队列
    void refreshPlayQueue();
    
    // 获取下一个待播放的 Asset
    // interrupt: 可选的紧急插播内容
    std::optional<Asset> getNextAsset(const std::optional<Interrupt>& interrupt = std::nullopt);

    // 获取当前正在播放的 Asset
    std::optional<Asset> getCurrentAsset() const;

    // 设置存储目录
    void setStorageDir(const std::string& path);
    
    // 清理存储空间 (LRU)
    void cleanStorage(long long maxBytes);

private:
    // 内部使用的无锁版本插播方法，必须在持有 queueMutex_ 时调用
    bool triggerInterruptLocked(const Interrupt& interrupt);

    // 播放列表 (内存中维护的队列)
    std::deque<PlayItem> playItems_;
    mutable std::mutex queueMutex_;
    const size_t MAX_QUEUE_SIZE = 5;
    Database db_;
    std::map<std::string, int> slotPlaybackState_; // 键: "策略ID_时间段ID", 值: 当前索引
    std::string storageDir_ = "resources/test"; // 默认为 resources/test 目录
    std::optional<Asset> currentAsset_;
};

#endif
