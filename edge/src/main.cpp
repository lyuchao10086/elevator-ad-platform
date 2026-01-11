// main.cpp - 最终的播放器入口
#include "Video_Player.h"
#include <iostream>
#include <chrono>  
#include <thread>

// 禁用SDL的main重定义
#ifdef main
#undef main
#endif

int main(int argc, char* argv[]) {
    std::cout << "=== 智能广告播放器 ===" << std::endl;

    std::string video_file = "test.mp4";

    // 检查文件是否存在
    FILE* test = fopen(video_file.c_str(), "rb");
    if (!test) {
        std::cout << "未找到test.mp4，创建测试视频..." << std::endl;
        system("ffmpeg -f lavfi -i testsrc=size=640x480:rate=30:duration=10 -c:v libx264 -pix_fmt yuv420p test.mp4 -y 2>nul");
    }
    else {
        fclose(test);
    }

    // 创建播放器
    VideoPlayer player;

    std::cout << "\n1. 加载视频文件..." << std::endl;
    if (!player.Load(video_file)) {
        std::cerr << "加载视频失败！" << std::endl;
        std::cout << "按Enter退出..." << std::endl;
        std::cin.get();
        return -1;
    }

    std::cout << "\n2. 开始播放..." << std::endl;
    std::cout << "   控制说明:" << std::endl;
    std::cout << "   - 空格键: 暂停/继续" << std::endl;
    std::cout << "   - ESC键: 退出" << std::endl;
    std::cout << "   - 关闭窗口: 退出" << std::endl;

    if (!player.Play()) {
        std::cerr << "播放失败！" << std::endl;
        std::cout << "按Enter退出..." << std::endl;
        std::cin.get();
        return -1;
    }

    std::cout << "\n3. 播放中..." << std::endl;

    // 等待播放结束
    while (player.IsPlaying() || player.IsWindowOpen()) {
        std::this_thread::sleep_for(std::chrono::milliseconds(100));

        // 每5秒显示一次状态
        static auto last_report = std::chrono::steady_clock::now();
        auto now = std::chrono::steady_clock::now();
        if (std::chrono::duration_cast<std::chrono::seconds>(now - last_report).count() >= 5) {
            std::cout << "播放状态: "
                << (player.IsPlaying() ? "播放中" : "停止")
                << (player.IsPaused() ? " (暂停)" : "")
                << std::endl;
            last_report = now;
        }
    }

    std::cout << "\n4. 播放结束！" << std::endl;
    std::cout << "按Enter退出..." << std::endl;
    std::cin.get();

    return 0;
}