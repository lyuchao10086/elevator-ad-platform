#ifndef ADVERTISEMENT_HPP
#define ADVERTISEMENT_HPP

#include <string>
#include <sstream>
#include "nlohmann/json.hpp"

using json = nlohmann::json;

/**
 * @brief 广告素材对象
 * 对应 Ads.json 中的单个广告条目
 */
class Advertisement {
private:
    std::string ad_id;
    std::string type;
    std::string filename;
    std::string md5;
    int duration;
    long long bytes;

public:
    // 默认构造函数
    Advertisement() : duration(0), bytes(0) {}

    // 全参构造函数
    Advertisement(std::string id, std::string t, std::string f, std::string m, int d, long long b)
        : ad_id(std::move(id)), type(std::move(t)), filename(std::move(f)), md5(std::move(m)), 
          duration(d), bytes(b) {}

    // Getters
    std::string getAdId() const { return ad_id; }
    std::string getType() const { return type; }
    std::string getFilename() const { return filename; }
    std::string getMd5() const { return md5; }
    int getDuration() const { return duration; }
    long long getBytes() const { return bytes; }

    // Setters
    void setAdId(const std::string& id) { ad_id = id; }
    void setType(const std::string& t) { type = t; }
    void setFilename(const std::string& f) { filename = f; }
    void setMd5(const std::string& m) { md5 = m; }
    void setDuration(int d) { duration = d; }
    void setBytes(long long b) { bytes = b; }

    /**
     * @brief 转换为字符串表示 (JSON 格式)
     */
    std::string toString() const {
        json j = *this;
        return j.dump(4); // 缩进4空格
    }

    /**
     * @brief 从 JSON 对象构造
     * @param j JSON 对象
     */
    static Advertisement fromJson(const json& j) {
        return j.get<Advertisement>();
    }

    /**
     * @brief 序列化为 JSON 对象
     */
    json toJson() const {
        return *this;
    }

    // nlohmann/json 宏，用于自动生成序列化/反序列化代码
    // 必须在类内部定义，以便访问私有成员
    NLOHMANN_DEFINE_TYPE_INTRUSIVE(Advertisement, ad_id, type, filename, md5, duration, bytes)
};

#endif // ADVERTISEMENT_HPP
