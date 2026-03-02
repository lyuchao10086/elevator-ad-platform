#include "ScheduleManager.hpp"
#include "nlohmann/json.hpp"
#include <optional>
#include <ctime>
#include <iomanip>
#include <sstream>
#include <algorithm>
#include <filesystem>

ScheduleManager::ScheduleManager(const std::string& dbPath) : db_(dbPath) {
    clearPlayQueue();
}

void ScheduleManager::initSchema() {
    db_.execute("PRAGMA foreign_keys = ON;");
    db_.execute(R"(
        CREATE TABLE IF NOT EXISTS assets (
            id TEXT PRIMARY KEY,
            type TEXT,
            filename TEXT,
            md5 TEXT,
            duration INTEGER,
            bytes INTEGER,
            last_played_time INTEGER DEFAULT 0
        );
    )");
    
    db_.execute(R"(
        CREATE TABLE IF NOT EXISTS schedules (
            policy_id TEXT PRIMARY KEY,
            effective_date TEXT,
            download_base_url TEXT,
            default_volume INTEGER,
            download_retry_count INTEGER,
            report_interval_sec INTEGER
        );
    )");
    db_.execute(R"(
        CREATE TABLE IF NOT EXISTS interrupts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            schedule_policy_id TEXT NOT NULL,
            trigger_type TEXT,
            ad_id TEXT,
            priority INTEGER DEFAULT 5,
            play_mode TEXT,
            FOREIGN KEY(schedule_policy_id) REFERENCES schedules(policy_id) ON DELETE CASCADE
        );
    )");
    db_.execute(R"(
        CREATE TABLE IF NOT EXISTS time_slots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            schedule_policy_id TEXT NOT NULL,
            slot_id INTEGER,
            time_range TEXT,
            volume INTEGER,
            priority INTEGER DEFAULT 5,
            loop_mode TEXT,
            playlist TEXT,
            FOREIGN KEY(schedule_policy_id) REFERENCES schedules(policy_id) ON DELETE CASCADE
        );
    )");
    // 创建播放队列表
    db_.execute(R"(
        CREATE TABLE IF NOT EXISTS play_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_id TEXT NOT NULL,
            priority INTEGER DEFAULT 5,
            is_interrupt INTEGER,
            source_id TEXT,
            created_at INTEGER
        );
    )");
}

void ScheduleManager::clearAll() {
    db_.execute("DELETE FROM play_items;");
    db_.execute("DELETE FROM time_slots;");
    db_.execute("DELETE FROM interrupts;");
    db_.execute("DELETE FROM schedules;");
    db_.execute("DELETE FROM assets;");
}

void ScheduleManager::clearPlayQueue() {
    try {
        // 检查表是否存在
        db_.execute("DELETE FROM play_items;");
    } catch (...) {
        // 忽略表不存在的错误
    }
}

void ScheduleManager::insertAsset(const Asset& asset) {
    std::string sql = "INSERT OR REPLACE INTO assets (id, type, filename, md5, duration, bytes, last_played_time) VALUES ('" +
        asset.getId() + "','" +
        asset.getType() + "','" +
        asset.getFilename() + "','" +
        asset.getMd5() + "'," +
        std::to_string(asset.getDuration()) + "," +
        std::to_string(asset.getBytes()) + "," +
        std::to_string(asset.getLastPlayedTime()) + ");";
    db_.execute(sql);
}

std::optional<Asset> ScheduleManager::getAsset(const std::string& id) const {
    auto rows = db_.query("SELECT id,type,filename,md5,duration,bytes,last_played_time FROM assets WHERE id='" + id + "';");
    if (rows.empty()) return std::nullopt;
    
    long long lastPlayed = 0;
    try {
        if (!rows[0]["last_played_time"].empty()) {
            lastPlayed = std::stoll(rows[0]["last_played_time"]);
        }
    } catch (...) {}

    nlohmann::json j = {
        {"id", rows[0]["id"]},
        {"type", rows[0]["type"]},
        {"filename", rows[0]["filename"]},
        {"md5", rows[0]["md5"]},
        {"duration", std::stoi(rows[0]["duration"])},
        {"bytes", std::stoll(rows[0]["bytes"])},
        {"last_played_time", lastPlayed}
    };
    return Asset(j);
}

void ScheduleManager::updateAsset(const Asset& asset) {
    insertAsset(asset);
}

void ScheduleManager::deleteAsset(const std::string& id) {
    db_.execute("DELETE FROM assets WHERE id='" + id + "';");
}

void ScheduleManager::insertSchedule(const Schedule& schedule) {
    db_.execute("BEGIN;");
    try {
        std::string policyId = schedule.getPolicyId();
        // 清理旧的子表数据，防止重复
        db_.execute("DELETE FROM time_slots WHERE schedule_policy_id='" + policyId + "';");
        db_.execute("DELETE FROM interrupts WHERE schedule_policy_id='" + policyId + "';");

        // 插入/更新 Schedules 表
        std::string schedSql = "INSERT OR REPLACE INTO schedules (policy_id,effective_date,download_base_url,default_volume,download_retry_count,report_interval_sec) VALUES ('" +
            schedule.getPolicyId() + "','" +
            schedule.getEffectiveDate() + "','" +
            schedule.getDownloadBaseUrl() + "'," +
            std::to_string(schedule.getDefaultVolume()) + "," +
            std::to_string(schedule.getDownloadRetryCount()) + "," +
            std::to_string(schedule.getReportIntervalSec()) + ");";
        db_.execute(schedSql);

        // 插入 Interrupts
        const auto& interrupt = schedule.getInterrupts();
        std::string intrSql = "INSERT INTO interrupts (schedule_policy_id,trigger_type,ad_id,priority,play_mode) VALUES ('" +
            schedule.getPolicyId() + "','" +
            interrupt.getTriggerType() + "','" +
            interrupt.getAdId() + "'," +
            std::to_string(interrupt.getPriority()) + ",'" +
            interrupt.getPlayMode() + "');";
        db_.execute(intrSql);

        // 插入 TimeSlots
        for (const auto& slot : schedule.getTimeSlots()) {
            json playlistJ = slot.getPlaylist();
            std::string playlistStr = playlistJ.dump();
            
            std::string slotSql = "INSERT INTO time_slots (schedule_policy_id,slot_id,time_range,volume,priority,loop_mode,playlist) VALUES ('" +
                schedule.getPolicyId() + "'," +
                std::to_string(slot.getSlotId()) + ",'" +
                slot.getTimeRange() + "'," +
                std::to_string(slot.getVolume()) + "," +
                std::to_string(slot.getPriority()) + ",'" +
                slot.getLoopMode() + "','" +
                playlistStr + "');";
            db_.execute(slotSql);
        }

        db_.execute("COMMIT;");
    } catch (...) {
        db_.execute("ROLLBACK;");
        throw;
    }
}

std::optional<Schedule> ScheduleManager::getSchedule(const std::string& policyId) {
    auto srows = db_.query("SELECT policy_id,effective_date,download_base_url,default_volume,download_retry_count,report_interval_sec FROM schedules WHERE policy_id='" + policyId + "';");
    if (srows.empty()) return std::nullopt;
    nlohmann::json sj = {
        {"policy_id", srows[0]["policy_id"]},
        {"effective_date", srows[0]["effective_date"]},
        {"download_base_url", srows[0]["download_base_url"]},
        {"default_volume", std::stoi(srows[0]["default_volume"])},
        {"download_retry_count", std::stoi(srows[0]["download_retry_count"])},
        {"report_interval_sec", std::stoi(srows[0]["report_interval_sec"])}
    };
    auto irows = db_.query("SELECT trigger_type,ad_id,priority,play_mode FROM interrupts WHERE schedule_policy_id='" + policyId + "' LIMIT 1;");
    if (!irows.empty()) {
        nlohmann::json ij = {
            {"trigger_type", irows[0]["trigger_type"]},
            {"ad_id", irows[0]["ad_id"]},
            {"priority", std::stoi(irows[0]["priority"])},
            {"play_mode", irows[0]["play_mode"]}
        };
        sj["interrupts"] = ij;
    } else {
        sj["interrupts"] = nlohmann::json::object();
    }
    sj["time_slots"] = nlohmann::json::array();
    auto trows = db_.query("SELECT id,slot_id,time_range,volume,priority,loop_mode,playlist FROM time_slots WHERE schedule_policy_id='" + policyId + "' ORDER BY id ASC;");
    for (const auto& row : trows) {
        // int tsid = std::stoi(row.at("id")); // No longer needed
        nlohmann::json slotJ = {
            {"slot_id", std::stoi(row.at("slot_id"))},
            {"time_range", row.at("time_range")},
            {"volume", std::stoi(row.at("volume"))},
            {"priority", std::stoi(row.at("priority"))},
            {"loop_mode", row.at("loop_mode")}
        };
        
        std::string playlistStr = row.at("playlist");
        if (!playlistStr.empty()) {
             slotJ["playlist"] = json::parse(playlistStr);
        } else {
             slotJ["playlist"] = json::array();
        }

        sj["time_slots"].push_back(slotJ);
    }
    return Schedule(sj);
}

void ScheduleManager::updateSchedule(const Schedule& schedule) {
    insertSchedule(schedule);
}

void ScheduleManager::deleteSchedule(const std::string& policyId) {
    db_.execute("DELETE FROM schedules WHERE policy_id='" + policyId + "';");
}

void ScheduleManager::syncSchedule(const std::string& jsonStr) {
    try {
        auto j = nlohmann::json::parse(jsonStr);
        
        if (j.is_array()) {
            for (const auto& item : j) {
                Schedule schedule(item);
                insertSchedule(schedule);
            }
        } else if (j.is_object()) {
            Schedule schedule(j);
            insertSchedule(schedule);
        } else {
             throw std::runtime_error("JSON must be an object or an array of objects");
        }
    } catch (const nlohmann::json::parse_error& e) {
        throw std::runtime_error("Invalid JSON format: " + std::string(e.what()));
    } catch (const std::exception& e) {
        throw std::runtime_error("Failed to load schedule from JSON: " + std::string(e.what()));
    }
}

static bool isTimeInRange(const std::string& range, const std::tm& now) {
    int startH, startM, startS, endH, endM, endS;
    // 格式为 HH:MM:SS-HH:MM:SS
    // 或者处理更简单的 HH:MM
    // JSON 示例为 "08:00:00-10:00:00"
    if (sscanf(range.c_str(), "%d:%d:%d-%d:%d:%d", &startH, &startM, &startS, &endH, &endM, &endS) == 6) {
        int nowSec = now.tm_hour * 3600 + now.tm_min * 60 + now.tm_sec;
        int startSec = startH * 3600 + startM * 60 + startS;
        int endSec = endH * 3600 + endM * 60 + endS;
        if (endSec < startSec) endSec += 24 * 3600; // 跨午夜处理
        return nowSec >= startSec && nowSec <= endSec;
    }
    return false;
}

std::optional<Asset> ScheduleManager::getNextAsset(const std::optional<Interrupt>& interrupt) {
    std::lock_guard<std::mutex> lock(queueMutex_);

    // 处理紧急插播 (如果有)
    if (interrupt.has_value()) {
        triggerInterruptLocked(interrupt.value());
    }

    // 维护常规播放队列 (补充至 MAX_QUEUE_SIZE)
    while (playItems_.size() < MAX_QUEUE_SIZE) {
        // 获取当前时间
        std::time_t t = std::time(nullptr);
        std::tm now = *std::localtime(&t);
        char dateStr[11];
        std::strftime(dateStr, sizeof(dateStr), "%Y-%m-%d", &now);
        
        // 查询今日有效的日程策略
        std::string sql = "SELECT s.policy_id, t.slot_id, t.time_range, t.priority, t.loop_mode, t.playlist "
                          "FROM time_slots t "
                          "JOIN schedules s ON t.schedule_policy_id = s.policy_id "
                          "WHERE s.effective_date <= '" + std::string(dateStr) + "'";
                          
        auto results = db_.query(sql);
        
        struct Candidate {
            std::string policyId;
            int slotId;
            int priority;
            std::string loopMode;
            std::vector<std::string> playlist;
        };
        
        std::vector<Candidate> candidates;
        
        // 筛选符合当前时间段的候选
        for (const auto& row : results) {
            std::string range = row.at("time_range");
            if (isTimeInRange(range, now)) {
                Candidate c;
                c.policyId = row.at("policy_id");
                c.slotId = std::stoi(row.at("slot_id"));
                c.priority = std::stoi(row.at("priority"));
                c.loopMode = row.at("loop_mode");
                
                try {
                    auto j = nlohmann::json::parse(row.at("playlist"));
                    c.playlist = j.get<std::vector<std::string>>();
                } catch (...) { continue; }

                if (!c.playlist.empty()) {
                    candidates.push_back(c);
                }
            }
        }
        
        if (candidates.empty()) break; // 无可播放资产，停止填充
        
        // 按优先级降序排序
        std::sort(candidates.begin(), candidates.end(), [](const Candidate& a, const Candidate& b) {
            return a.priority > b.priority;
        });
        
        const auto& best = candidates[0];
        
        // 计算播放索引
        std::string stateKey = best.policyId + "_" + std::to_string(best.slotId);
        int index = 0;
        
        if (best.loopMode == "random") {
            index = std::rand() % best.playlist.size();
        } else {
            if (slotPlaybackState_.count(stateKey)) {
                index = (slotPlaybackState_[stateKey] + 1) % best.playlist.size();
            }
            slotPlaybackState_[stateKey] = index;
        }
        
        std::string assetId = best.playlist[index];
        
        // 创建新的播放项
        PlayItem newItem(assetId, best.priority, false, best.policyId);
        newItem.setCreatedAt(std::chrono::system_clock::to_time_t(std::chrono::system_clock::now()));
        
        // 插入到队列尾部
        playItems_.push_back(newItem);
        
        // 存入数据库
        std::string insertSql = "INSERT INTO play_items (asset_id, priority, is_interrupt, source_id, created_at) VALUES ('" +
            newItem.getAssetId() + "'," +
            std::to_string(newItem.getPriority()) + "," +
            "0,'" + // is_interrupt = 0
            newItem.getSourceId() + "'," +
            std::to_string(newItem.getCreatedAt()) + ");";
            
        try {
            db_.execute(insertSql);
        } catch (...) {}
    }
    
    // 取出播放列表首项
    if (playItems_.empty()) {
        currentAsset_ = std::nullopt;
        return std::nullopt;
    }
    
    PlayItem item = playItems_.front();
    playItems_.pop_front();
    
    // 从数据库删除队首项
    std::string subQuery = "SELECT id FROM play_items WHERE asset_id='" + item.getAssetId() + 
                           "' AND created_at=" + std::to_string(item.getCreatedAt()) + 
                           " LIMIT 1";
    db_.execute("DELETE FROM play_items WHERE id IN (" + subQuery + ");");
    
    // 更新最后播放时间
    auto assetOpt = getAsset(item.getAssetId());
    if (assetOpt) {
        currentAsset_ = assetOpt;
        std::time_t nowTime = std::time(nullptr);
        std::string updateSql = "UPDATE assets SET last_played_time = " + std::to_string(nowTime) + 
                                " WHERE id = '" + item.getAssetId() + "'";
        db_.execute(updateSql);
        return *assetOpt;
    }
    
    currentAsset_ = std::nullopt;
    return std::nullopt;
}

bool ScheduleManager::triggerInterrupt(const Interrupt& interrupt) {
    std::lock_guard<std::mutex> lock(queueMutex_);
    return triggerInterruptLocked(interrupt);
}

bool ScheduleManager::triggerInterruptLocked(const Interrupt& interrupt) {
    auto assetOpt = getAsset(interrupt.getAdId());
    if (!assetOpt) return false;

    // 创建插播项
    PlayItem item(interrupt.getAdId(), interrupt.getPriority(), true, "INTERRUPT_" + interrupt.getAdId());
    item.setCreatedAt(std::chrono::system_clock::to_time_t(std::chrono::system_clock::now()));
    
    // 插入播放队列头部
    playItems_.push_front(item);
    
    // 插入数据库
    std::string sql = "INSERT INTO play_items (asset_id, priority, is_interrupt, source_id, created_at) VALUES ('" +
        item.getAssetId() + "'," +
        std::to_string(item.getPriority()) + "," +
        (item.isInterrupt() ? "1" : "0") + ",'" +
        item.getSourceId() + "'," +
        std::to_string(item.getCreatedAt()) + ");";
    
    try {
        db_.execute(sql);
        return true;
    } catch (...) {
        return false;
    }
}

std::vector<PlayItem> ScheduleManager::getPlayQueue() const {
    std::lock_guard<std::mutex> lock(queueMutex_);
    // 直接返回内存中的队列，它就是最新的 PlayItems
    std::vector<PlayItem> result;
    for (const auto& item : playItems_) {
        PlayItem fullItem = item;
        // 尝试填充 Asset 信息用于显示
        auto assetOpt = getAsset(item.getAssetId());
        if (assetOpt) {
            fullItem.setAsset(*assetOpt);
        }
        result.push_back(fullItem);
    }
    return result;
}

void ScheduleManager::refreshPlayQueue() {
    std::lock_guard<std::mutex> lock(queueMutex_);
    playItems_.clear();
    clearPlayQueue(); // 清空 DB
    getNextAsset(); // 刷新队列
}

std::optional<Asset> ScheduleManager::getCurrentAsset() const {
    std::lock_guard<std::mutex> lock(queueMutex_);
    return currentAsset_;
}

void ScheduleManager::setStorageDir(const std::string& path) {
    storageDir_ = path;
}

void ScheduleManager::cleanStorage(long long maxBytes) {
    // 获取当前总大小
    long long currentSize = 0;
    try {
        // 查询 assets 表中所有 bytes 字段的总和
        auto result = db_.query("SELECT SUM(bytes) as total_bytes FROM assets");
        if (!result.empty() && !result[0]["total_bytes"].empty()) {
            currentSize = std::stoll(result[0]["total_bytes"]);
        }
    } catch (...) {
        currentSize = 0;
    }

    if (currentSize <= maxBytes) return;

    // 循环删除直到满足条件
    // 每次查询最久未使用的文件 (last_played_time 最小)
    // 优先删除 last_played_time = 0 (从未播放)
    while (currentSize > maxBytes) {
        std::string sql = "SELECT id, filename, bytes FROM assets ORDER BY last_played_time ASC LIMIT 1";
        auto candidates = db_.query(sql);
        
        if (candidates.empty()) break; // 没有更多文件可删
        
        const auto& candidate = candidates[0];
        std::string id = candidate.at("id");
        std::string filename = candidate.at("filename");
        long long bytes = 0;
        try {
            bytes = std::stoll(candidate.at("bytes"));
        } catch (...) {}
        
        // 删除数据库记录
        deleteAsset(id);
        
        // 删除磁盘文件
        namespace fs = std::filesystem;
        fs::path filePath = fs::path(storageDir_) / filename;
        std::error_code ec;
        if (fs::exists(filePath, ec)) {
            fs::remove(filePath, ec);
        }
        
        // 更新当前大小
        currentSize -= bytes;
    }
}
