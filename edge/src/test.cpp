#include <iostream>
#include <string>
#include <vector>
#include <cassert>
#include <filesystem>
#include <fstream>
#include <thread>
#include <chrono>
#include "ScheduleManager.hpp"
#include "models/Asset.hpp"
#include "models/Schedule.hpp"
#include "models/Interrupt.hpp"
#include "models/TimeSlot.hpp"
#include "nlohmann/json.hpp"

using json = nlohmann::json;
namespace fs = std::filesystem;

// 全局配置
// 注意：测试程序在 build 目录下运行，为了让用户在 IDE 文件资源管理器中看到变化，
// 我们将测试目录指向项目根目录下的 resources/test
static const std::string TEST_DB_PATH = "test_schedule.db";
static const std::string TEST_STORAGE_DIR = "../resources/test";
static const std::string REAL_RESOURCES_DIR = "../resources";
static const std::string MEDIA_SOURCE_DIR = "../resources/test";

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

// 辅助函数：打印带颜色的日志
void printSuccess(const std::string& msg) {
    std::cout << "\033[1;32m✅ " << msg << "\033[0m" << std::endl;
}

void printError(const std::string& msg) {
    std::cerr << "\033[1;31m❌ " << msg << "\033[0m" << std::endl;
}

void printInfo(const std::string& msg) {
    std::cout << "\033[1;34mℹ️ " << msg << "\033[0m" << std::endl;
}

void printStep(const std::string& stepName) {
    std::cout << "\n========================================\n";
    std::cout << "[TEST] " << stepName << "\n";
    std::cout << "========================================\n";
}

// -----------------------------------------------------------------------------
// 模块化测试函数
// -----------------------------------------------------------------------------

// 1. 初始化测试环境
void initEnvironment(ScheduleManager& manager) {
    printStep("初始化测试环境");
    
    // 打印当前工作目录和测试存储目录的绝对路径
    printInfo("当前工作目录: " + fs::current_path().string());
    printInfo("测试存储目录 (绝对路径): " + fs::absolute(fs::path(TEST_STORAGE_DIR)).string());

    try {
        // 1. 初始化数据库
        manager.initSchema();
        manager.clearAll();
        printSuccess("数据库已重置");

        // 2. 准备测试用的媒体目录 (复制真实文件)
        if (fs::exists(TEST_STORAGE_DIR)) {
            fs::remove_all(TEST_STORAGE_DIR);
        }
        fs::create_directories(TEST_STORAGE_DIR);
        
        // 复制 resources 下的媒体文件到 test_run
        // 注意：只复制 Assets.json 中引用的媒体文件，或者简单点复制所有文件
        if (fs::exists(MEDIA_SOURCE_DIR)) {
            for (const auto& entry : fs::directory_iterator(MEDIA_SOURCE_DIR)) {
                if (entry.is_regular_file()) {
                    std::string filename = entry.path().filename().string();
                    if (filename != "Assets.json" && filename != "Schedule.json" && filename != ".DS_Store") {
                        fs::copy_file(entry.path(), fs::path(TEST_STORAGE_DIR) / filename, fs::copy_options::overwrite_existing);
                        // printInfo("已复制文件: " + filename);
                    }
                }
            }
        } else {
            printError("未找到媒体源目录: " + MEDIA_SOURCE_DIR);
        }
        
        manager.setStorageDir(TEST_STORAGE_DIR);
        printSuccess("测试媒体目录已准备: " + TEST_STORAGE_DIR);
        
    } catch (const std::exception& e) {
        printError("初始化环境失败: " + std::string(e.what()));
    }
}

// 2. 导入真实数据
void importRealData(ScheduleManager& manager) {
    printStep("导入真实数据 (从 resources/*.json)");
    try {
        // 1. 导入 Assets
        std::string assetsJsonStr = readFile(fs::path(REAL_RESOURCES_DIR) / "Assets.json");
        json assetsValue = json::parse(assetsJsonStr);
        
        int assetCount = 0;
        if (assetsValue.contains("assets") && assetsValue["assets"].is_array()) {
            for (const auto& item : assetsValue["assets"]) {
                Asset asset(item);
                manager.insertAsset(asset);
                assetCount++;
            }
        }
        printSuccess("已导入 " + std::to_string(assetCount) + " 个资产");

        // 2. 导入 Schedule
        std::string scheduleJsonStr = readFile(fs::path(REAL_RESOURCES_DIR) / "Schedule.json");
        manager.syncSchedule(scheduleJsonStr);
        
        // 验证导入
        json schedJson = json::parse(scheduleJsonStr);
        std::string policyId = schedJson["policy_id"];
        if (manager.getSchedule(policyId)) {
            printSuccess("已导入日程策略: " + policyId);
        } else {
            printError("日程导入失败");
        }

    } catch (const std::exception& e) {
        printError("导入数据失败: " + std::string(e.what()));
    }
}

// 3. 测试 Asset 操作 (使用真实 ID)
void testAssetCRUD(ScheduleManager& manager) {
    printStep("测试 Asset 增删改查");
    std::string targetId = "AD_NIKE_01";
    
    // GET
    auto asset = manager.getAsset(targetId);
    if (asset) {
        printSuccess("查询成功: " + asset->getId() + " (" + asset->getFilename() + ")");
        printInfo("当前时长: " + std::to_string(asset->getDuration()) + "s");
    } else {
        printError("未找到资产: " + targetId + " (请先执行导入数据)");
        return;
    }

    // UPDATE
    int originalDuration = asset->getDuration();
    asset->setDuration(999);
    manager.updateAsset(*asset);
    
    auto updated = manager.getAsset(targetId);
    if (updated && updated->getDuration() == 999) {
        printSuccess("更新时长成功: 999s");
    } else {
        printError("更新失败");
    }
    
    // REVERT
    asset->setDuration(originalDuration);
    manager.updateAsset(*asset);
    printInfo("已恢复原始时长");
}

// 4. 测试 Schedule 操作
void testScheduleCRUD(ScheduleManager& manager) {
    printStep("测试 Schedule 增删改查");
    std::string targetId = "POL_SH_20260112_V1";
    
    auto schedule = manager.getSchedule(targetId);
    if (schedule) {
        printSuccess("查询成功: " + schedule->getPolicyId());
        printInfo("包含时间段数量: " + std::to_string(schedule->getTimeSlots().size()));
        
        if (!schedule->getTimeSlots().empty()) {
            printInfo("第一个时间段播放列表: ");
            for (const auto& id : schedule->getTimeSlots()[0].getPlaylist()) {
                std::cout << "  - " << id << "\n";
            }
        }
    } else {
        printError("未找到日程: " + targetId + " (请先执行导入数据)");
    }
}

// 5. 测试播放策略 (getNextAsset & PlayQueue)
void testPlaybackPolicy(ScheduleManager& manager) {
    printStep("测试播放策略 & 播放队列");
    
    // Helper lambda to print queue
    auto printQueue = [&](const std::string& prefix) {
        auto queue = manager.getPlayQueue();
        printInfo(prefix + " [当前队列长度: " + std::to_string(queue.size()) + "]");
        for (const auto& item : queue) {
            std::string tag = item.isInterrupt() ? "[插播]" : "[计划]";
            std::cout << "    " << tag << " AssetID: " << item.getAsset().getId() 
                      << " | Priority: " << item.getPriority() 
                      << " | Source: " << item.getSourceId() << "\n";
        }
        std::cout << std::endl;
    };

    // -------------------------------------------------------------------------
    // Case 1: 常规日程播放 (无参调用)
    // -------------------------------------------------------------------------
    std::cout << "\n>>> Case 1: 常规日程播放 (getNextAsset 无参)" << std::endl;
    printQueue("初始状态");
    
    printInfo("执行: manager.getNextAsset()...");
    auto asset1 = manager.getNextAsset();
    
    if (asset1) {
        printSuccess("获取成功 -> Asset ID: " + asset1->getId());
        std::cout << "    Type: " << asset1->getType() << "\n"
                  << "    Filename: " << asset1->getFilename() << "\n"
                  << "    Duration: " << asset1->getDuration() << "s\n";

        // 验证 getCurrentAsset
        auto current = manager.getCurrentAsset();
        if (current && current->getId() == asset1->getId()) {
             printSuccess("验证通过: getCurrentAsset() 正确返回了当前播放内容");
        } else {
             printError("验证失败: getCurrentAsset() 未返回预期内容");
        }
    } else {
        printError("获取失败 (无可用日程)");
    }
    printQueue("调用后状态");

    // -------------------------------------------------------------------------
    // Case 2: 手动触发插播 (triggerInterrupt)
    // -------------------------------------------------------------------------
    std::cout << ">>> Case 2: 手动触发插播 (triggerInterrupt + getNextAsset)" << std::endl;
    
    std::string interruptId1 = "AD_COKE_CNY";
    printInfo("执行: triggerInterrupt(Asset: " + interruptId1 + ", Priority: 9)...");
    Interrupt intr1("command", interruptId1, 9, "cut_in");
    
    if (manager.triggerInterrupt(intr1)) {
        printSuccess("插播指令下发成功");
        printQueue("插播后状态 (应在队首)");
        
        printInfo("执行: manager.getNextAsset() 获取插播内容...");
        auto asset2 = manager.getNextAsset();
        if (asset2 && asset2->getId() == interruptId1) {
            printSuccess("验证通过: 正确获取到了插播广告 " + interruptId1);
            
            // 验证 getCurrentAsset
            auto current = manager.getCurrentAsset();
            if (current && current->getId() == interruptId1) {
                 printSuccess("验证通过: getCurrentAsset() 也返回了插播内容");
            } else {
                 printError("验证失败: getCurrentAsset() 未同步更新");
            }
        } else {
            printError("验证失败: 未获取到预期插播内容");
        }
    } else {
        printError("插播失败 (可能是 Asset 不存在)");
    }
    printQueue("消费插播后状态");

    // -------------------------------------------------------------------------
    // Case 3: 直接带参调用 (getNextAsset with args)
    // -------------------------------------------------------------------------
    std::cout << ">>> Case 3: 直接带参调用 (getNextAsset 带 Interrupt 参数)" << std::endl;
    
    std::string interruptId2 = "AD_NIKE_01";
    printInfo("执行: getNextAsset(Interrupt: " + interruptId2 + ")...");
    Interrupt intr2("command", interruptId2, 9, "cut_in");
    
    auto asset3 = manager.getNextAsset(intr2);
    
    if (asset3) {
        if (asset3->getId() == interruptId2) {
            printSuccess("验证通过: getNextAsset 优先返回了参数中的插播内容");
            std::cout << "    Asset ID: " << asset3->getId() << "\n"
                      << "    Type: " << asset3->getType() << "\n";
            
            // 验证 getCurrentAsset
            auto current = manager.getCurrentAsset();
            if (current && current->getId() == interruptId2) {
                 printSuccess("验证通过: getCurrentAsset() 也返回了插播内容");
            } else {
                 printError("验证失败: getCurrentAsset() 未同步更新");
            }
        } else {
            printError("验证失败: 返回了 " + asset3->getId() + " 而非 " + interruptId2);
        }
    } else {
        printError("获取失败");
    }
    
    // -------------------------------------------------------------------------
    // Case 4: 低优先级插播 (Low Priority Interrupt)
    // -------------------------------------------------------------------------
    std::cout << ">>> Case 4: 低优先级插播 (Priority: 1)" << std::endl;
    
    std::string interruptId3 = "AD_APP_PROMO";
    printInfo("执行: triggerInterrupt(Asset: " + interruptId3 + ", Priority: 1)...");
    // 注意：当前实现中，插播(triggerInterrupt)总是插入队首，不比较优先级。
    // 测试目的是验证即使优先级低，它仍然被插入到队首。
    Interrupt intr3("command", interruptId3, 1, "cut_in");
    
    if (manager.triggerInterrupt(intr3)) {
        printSuccess("插播指令下发成功");
        
        auto asset4 = manager.getNextAsset();
        if (asset4 && asset4->getId() == interruptId3) {
             printSuccess("验证通过: 低优先级插播也成功抢占 (插播总是优先)");
        } else {
             printError("验证失败: 低优先级插播未被优先播放");
        }
    } else {
        printError("插播失败");
    }

    // -------------------------------------------------------------------------
    // Case 5: 连续插播 (Sequential Interrupts) - LIFO 验证
    // -------------------------------------------------------------------------
    std::cout << ">>> Case 5: 连续插播 (先A后B -> 期望顺序 B, A)" << std::endl;
    
    // 使用已有的 ID，或者复用
    std::string intrIdA = "AD_COKE_CNY"; // A
    std::string intrIdB = "AD_NIKE_01";  // B
    
    printInfo("执行: 连续触发 A(" + intrIdA + ") 然后 B(" + intrIdB + ")...");
    
    manager.triggerInterrupt(Interrupt("cmd", intrIdA, 5, "cut_in"));
    manager.triggerInterrupt(Interrupt("cmd", intrIdB, 5, "cut_in"));
    
    // 获取第一个 (期望是 B，因为是 push_front，后进先出)
    auto assetFirst = manager.getNextAsset();
    bool firstIsB = (assetFirst && assetFirst->getId() == intrIdB);
    
    if (firstIsB) {
        printSuccess("第一次获取: " + assetFirst->getId() + " (符合预期: 后插播的先播)");
    } else {
        printError("第一次获取: " + (assetFirst ? assetFirst->getId() : "null") + " (预期: " + intrIdB + ")");
    }
    
    // 获取第二个 (期望是 A)
    auto assetSecond = manager.getNextAsset();
    bool secondIsA = (assetSecond && assetSecond->getId() == intrIdA);
    
    if (secondIsA) {
        printSuccess("第二次获取: " + assetSecond->getId() + " (符合预期: 先插播的后播)");
    } else {
        printError("第二次获取: " + (assetSecond ? assetSecond->getId() : "null") + " (预期: " + intrIdA + ")");
    }

    printQueue("最终状态");
}

// 6. 测试磁盘清理 (LRU)
void testLRUCleanup(ScheduleManager& manager) {
    printStep("测试磁盘清理 (LRU)");
    
    // 统计当前总大小
    long long totalBytes = 0;
    for (const auto& entry : fs::directory_iterator(TEST_STORAGE_DIR)) {
        if (entry.is_regular_file()) {
            totalBytes += entry.file_size();
        }
    }
    printInfo("当前存储目录总大小: " + std::to_string(totalBytes) + " bytes");
    
    if (totalBytes == 0) {
        printError("目录为空，无法测试清理 (请先初始化并导入数据)");
        return;
    }
    
    // 设置一个极小的限制，强制删除
    long long limitBytes = totalBytes / 2; 
    printInfo("设置限制为: " + std::to_string(limitBytes) + " bytes");
    
    // 为了确保 LRU 有效，我们需要让某些文件“被播放过”，某些没播放过
    // 模拟：更新 AD_NIKE_01 的播放时间为现在，其他为 0 (最老)
    try {
        long long now = std::chrono::system_clock::to_time_t(std::chrono::system_clock::now());
        std::string sql = "UPDATE assets SET last_played_time = " + std::to_string(now) + " WHERE id = 'AD_NIKE_01'";
        // 这里我们没有直接暴露 db_.execute，只能通过 getNextAsset 隐式更新
        // 或者我们假设 getNextAsset 刚刚被调用过 (在 step 5 中)
        
        // 执行清理
        manager.setStorageDir(TEST_STORAGE_DIR);
        manager.cleanStorage(limitBytes);
        
        // 验证
        long long newTotalBytes = 0;
        bool nikeExists = false;
        for (const auto& entry : fs::directory_iterator(TEST_STORAGE_DIR)) {
            if (entry.is_regular_file()) {
                newTotalBytes += entry.file_size();
                if (entry.path().filename() == "nike_2026_q1.mp4") {
                    nikeExists = true;
                }
            }
        }
        
        printInfo("清理后总大小: " + std::to_string(newTotalBytes) + " bytes");
        
        if (newTotalBytes <= limitBytes) {
            printSuccess("清理成功: 大小已降至限制以下");
        } else {
            printError("清理失败: 大小仍超出限制");
        }
        
    } catch (const std::exception& e) {
        printError("清理过程出错: " + std::string(e.what()));
    }
}

// -----------------------------------------------------------------------------
// 主菜单
// -----------------------------------------------------------------------------
void showMenu() {
    std::cout << "\n----------------------------------------\n";
    std::cout << " Schedule 模块交互式测试工具\n";
    std::cout << "----------------------------------------\n";
    std::cout << "1. 初始化测试环境 (重置DB & 复制文件)\n";
    std::cout << "2. 导入真实数据 (Assets.json & Schedule.json)\n";
    std::cout << "3. 测试 Asset 操作 (CRUD)\n";
    std::cout << "4. 测试 Schedule 操作 (CRUD)\n";
    std::cout << "5. 测试播放策略 (getNextAsset)\n";
    std::cout << "6. 测试磁盘清理 (LRU)\n";
    std::cout << "0. 退出\n";
    std::cout << "----------------------------------------\n";
    std::cout << "请输入选项: ";
}

int main() {
    ScheduleManager manager(TEST_DB_PATH);
    
    int choice = -1;
    while (choice != 0) {
        showMenu();
        if (!(std::cin >> choice)) {
            std::cin.clear();
            std::cin.ignore(std::numeric_limits<std::streamsize>::max(), '\n');
            continue;
        }
        
        switch (choice) {
            case 1: initEnvironment(manager); break;
            case 2: importRealData(manager); break;
            case 3: testAssetCRUD(manager); break;
            case 4: testScheduleCRUD(manager); break;
            case 5: testPlaybackPolicy(manager); break;
            case 6: testLRUCleanup(manager); break;
            case 0: std::cout << "退出程序。\n"; break;
            default: std::cout << "无效选项，请重试。\n"; break;
        }
    }
    
    return 0;
}
