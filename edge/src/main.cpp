#include <iostream>
#include <string>
#include <filesystem>
#include <fstream>
#include "EdgeManager.hpp"

namespace fs = std::filesystem;

int main(int argc, char* argv[]) {
    try {
        // 1. 确定配置文件路径
        std::string configPath = "config.json";
        if (argc > 1) {
            configPath = argv[1];
        }

        // 2. 初始化 EdgeManager
        EdgeManager manager;
        if (!manager.init(configPath)) {
            std::cerr << "EdgeManager 初始化失败，程序退出。" << std::endl;
            return 1;
        }

        // 3. 运行主循环
        manager.run();

    } catch (const std::exception& e) {
        std::cerr << "发生严重错误: " << e.what() << std::endl;
        return 1;
    }

    return 0;
}
