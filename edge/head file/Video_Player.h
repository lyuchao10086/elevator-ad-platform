// Video_Player.h
#pragma once
#include <string>
#include <memory>
#include <functional>

// SDL
#include <SDL.h>

extern "C" {
#include <libavformat/avformat.h>
#include <libavcodec/avcodec.h>
#include <libavutil/avutil.h>
#include <libswscale/swscale.h>
#include <libavutil/imgutils.h>
}

class VideoPlayer {
public:
    VideoPlayer();
    ~VideoPlayer();

    // 窗口管理
    void CreateWindow(const std::string& title, int width, int height);
    void CloseWindow();

    // 核心功能
    bool Load(const std::string& filepath);
    bool Play();
    bool Pause();
    bool Stop();
    void Seek(int64_t timestamp_ms);

    // 状态查询
    bool IsPlaying() const;
    bool IsPaused() const;
    bool IsWindowOpen() const;
    int64_t GetDuration() const;      // 毫秒
    int64_t GetCurrentPosition() const; // 毫秒

    // 视频信息
    int GetWidth() const;
    int GetHeight() const;
    double GetFrameRate() const;

    // 设置回调函数
    using FrameCallback = std::function<void(const uint8_t* data, int width, int height, int pitch)>;
    void SetFrameCallback(FrameCallback callback);

private:
    // 私有实现
    struct Impl;
    std::unique_ptr<Impl> pImpl;
};