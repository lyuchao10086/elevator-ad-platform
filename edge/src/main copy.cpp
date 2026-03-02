#include <iostream>
#include <fstream>
#include <sstream>
#include "Database.hpp"
#include "ScheduleManager.hpp"
#include "models/Asset.hpp"
#include "models/Interrupt.hpp"
#include "models/TimeSlot.hpp"
#include "models/Schedule.hpp"
#include "nlohmann/json.hpp"

using json = nlohmann::json;

// 辅助函数：读取文件内容
std::string readFile(const std::string& path) {
    std::ifstream ifs(path);
    if (!ifs.is_open()) {
        throw std::runtime_error("无法打开文件: " + path);
    }
    std::stringstream buffer;
    buffer << ifs.rdbuf();
    return buffer.str();
}

int main() {
    try {
        ScheduleManager manager("schedule.db");
        //初始化数据库表
        manager.initSchema();
        
        //清理旧数据
        manager.clearAll();

        //导入 resources文件夹中的数据到数据库
        std::string assetsJsonStr = readFile("resources/Assets.json");
        json assetsValue = json::parse(assetsJsonStr);
        
        if (assetsValue.contains("assets") && assetsValue["assets"].is_array()) {
            std::vector<Asset> assets;
            assetsValue.at("assets").get_to(assets);
            
            for (const auto& asset : assets) {
                manager.insertAsset(asset);
            }
        }

        std::string scheduleJsonStr = readFile("resources/Schedule.json");
        json scheduleValue = json::parse(scheduleJsonStr);
        Schedule schedule(scheduleValue);
        
        manager.insertSchedule(schedule);

    } catch (const json::parse_error& e) {
        std::cerr << "JSON 解析错误: " << e.what() << std::endl;
        return 1;
    } catch (const std::exception& e) {
        std::cerr << "发生错误: " << e.what() << std::endl;
        return 1;
    }

    return 0;
}
