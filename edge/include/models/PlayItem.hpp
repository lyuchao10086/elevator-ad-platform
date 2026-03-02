#ifndef PLAY_ITEM_HPP
#define PLAY_ITEM_HPP

#include <string>
#include "nlohmann/json.hpp"
#include "Asset.hpp"

using json = nlohmann::json;

/**
 * @brief 播放队列项实体类
 * 
 * 对应数据库 play_items 表
 */
class PlayItem {
public:
    PlayItem();
    PlayItem(const std::string& assetId, int priority, bool isInterrupt, const std::string& sourceId);
    explicit PlayItem(const json& j);

    // Getters
    int getId() const;
    std::string getAssetId() const;
    int getPriority() const;
    bool isInterrupt() const;
    std::string getSourceId() const;
    long long getCreatedAt() const;
    
    // 关联的 Asset 对象 (非数据库字段，用于运行时携带信息)
    void setAsset(const Asset& asset);
    const Asset& getAsset() const;
    bool hasAsset() const;

    // Setters
    void setId(int id);
    void setAssetId(const std::string& assetId);
    void setPriority(int priority);
    void setIsInterrupt(bool isInterrupt);
    void setSourceId(const std::string& sourceId);
    void setCreatedAt(long long timestamp);

    json toJson() const;
    std::string toString() const;

private:
    int id_ = 0; // 数据库自增ID
    std::string asset_id_;
    int priority_ = 0;
    bool is_interrupt_ = false;
    std::string source_id_;
    long long created_at_ = 0;
    
    Asset asset_; // 内存缓存的 Asset 对象
    bool has_asset_ = false;
};

void to_json(json& j, const PlayItem& p);
void from_json(const json& j, PlayItem& p);

#endif // PLAY_ITEM_HPP
