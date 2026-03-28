#include <iostream>
#include <string>
#include <filesystem>
#include <fstream>
#include <vector>
#include "EdgeManager.hpp"
#include "Watchdog.hpp"
#ifdef _WIN32
#include <windows.h>
#endif

namespace fs = std::filesystem;

int main(int argc, char* argv[]) {
#ifdef _WIN32
    SetConsoleOutputCP(CP_UTF8);
    SetConsoleCP(CP_UTF8);
#endif
    try {
        std::string configPath = "config.json";
        bool isWatchdog = false;
        bool isPlayer = false;

        std::vector<std::string> args(argv + 1, argv + argc);
        for (size_t i = 0; i < args.size(); ++i) {
            if (args[i] == "--watchdog") {
                isWatchdog = true;
            } else if (args[i] == "--player") {
                isPlayer = true;
            } else if (args[i].find(".json") != std::string::npos) {
                configPath = args[i];
            }
        }

        if (isWatchdog) {
            // 守护进程模式
            Watchdog watchdog(configPath, argv[0]);
            watchdog.run();
        } else {
            // 播放器模式 (如果是由守护进程启动的，带有 --player 标记)
            EdgeManager manager;
            if (!manager.init(configPath, isPlayer)) {
                std::cerr << "EdgeManager 初始化失败，程序退出。" << std::endl;
                return 1;
            }
            manager.run();
        }

    } catch (const std::exception& e) {
        std::cerr << "发生严重错误: " << e.what() << std::endl;
        return 1;
    }

    return 0;
}
