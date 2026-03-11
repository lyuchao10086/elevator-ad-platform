/**
 * @file VideoPlayer.hpp
 * @brief 视频播放器接口类
 * @author Trae AI
 * @date 2026-03-05
 * 
 * 定义了基于 FFmpeg 和 SDL2 的视频播放器接口。
 * 支持视频解码、渲染、窗口管理、图片显示以及基本的播放控制。
 */

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

/**
 * @class VideoPlayer
 * @brief 视频播放器类
 * 
 * 封装了底层的 FFmpeg 解码和 SDL2 渲染逻辑。
 * 采用了 PIMPL (Pointer to Implementation) 模式，隐藏了实现细节和私有成员，
 * 保持头文件整洁，减少编译依赖。
 */
class VideoPlayer {
public:
    /**
     * @brief 构造函数
     * 初始化播放器资源
     */
    VideoPlayer();

    /**
     * @brief 析构函数
     * 释放播放器资源，关闭线程和窗口
     */
    ~VideoPlayer();

    // --- 窗口管理 ---

    /**
     * @brief 创建或重用 SDL 播放窗口
     * 
     * 如果窗口已存在，则只更新标题。
     * 
     * @param title 窗口标题
     * @param width 窗口宽度
     * @param height 窗口高度
     */
    void CreateWindow(const std::string& title, int width, int height);

    /**
     * @brief 关闭 SDL 窗口
     * 停止播放并销毁窗口资源
     */
    void CloseWindow();

    /**
     * @brief 设置窗口标题
     * 
     * @param title 新的窗口标题
     */
    void SetWindowTitle(const std::string& title);

    // --- 播放控制 ---

    /**
     * @brief 加载媒体文件
     * 
     * 初始化 FFmpeg 解码器，打开文件流。
     * 支持视频文件和图片文件。
     * 
     * @param filepath 媒体文件路径
     * @param duration_ms 指定播放时长(毫秒)。
     *                    - 对于视频：通常为 0，表示播放完整视频。若 >0，则达到时长后停止。
     *                    - 对于图片：必须 >0，表示图片显示的持续时间。
     * @return true 加载成功
     * @return false 加载失败
     */
    bool Load(const std::string& filepath, int64_t duration_ms = 0);

    /**
     * @brief 开始播放
     * 
     * 启动解码线程，开始处理媒体数据。
     * @return true 启动成功
     * @return false 启动失败
     */
    bool Play();

    /**
     * @brief 更新播放状态 (主线程调用)
     * 
     * 该方法必须在主线程中循环调用。
     * 负责处理 SDL 事件 (如窗口关闭、键盘输入) 和 视频帧渲染。
     * 解决了 macOS 上 UI 操作必须在主线程执行的问题。
     */
    void Update();

    /**
     * @brief 暂停/恢复播放
     * @return true 操作成功
     * @return false 操作失败 (如未在播放状态)
     */
    bool Pause();

    /**
     * @brief 停止播放
     * 
     * 停止解码线程，重置播放状态，但保留窗口。
     * @return true 成功
     */
    bool Stop();

    /**
     * @brief 跳转到指定时间戳
     * @param timestamp_ms 目标时间 (毫秒)
     */
    void Seek(int64_t timestamp_ms);

    // --- 状态查询 ---

    /**
     * @brief 是否正在播放
     */
    bool IsPlaying() const;

    /**
     * @brief 是否已暂停
     */
    bool IsPaused() const;

    /**
     * @brief 窗口是否打开
     */
    bool IsWindowOpen() const;

    /**
     * @brief 获取媒体总时长 (毫秒)
     */
    int64_t GetDuration() const;

    /**
     * @brief 获取当前播放位置 (毫秒)
     */
    int64_t GetCurrentPosition() const;

    // --- 视频信息 ---

    /**
     * @brief 获取视频宽度
     */
    int GetWidth() const;

    /**
     * @brief 获取视频高度
     */
    int GetHeight() const;

    /**
     * @brief 获取帧率
     */
    double GetFrameRate() const;

    // --- 数据回调 ---

    /**
     * @brief 视频帧数据回调函数类型
     * @param data YUV 数据指针
     * @param width 宽度
     * @param height 高度
     * @param pitch 跨度
     */
    using FrameCallback = std::function<void(const uint8_t* data, int width, int height, int pitch)>;

    /**
     * @brief 设置视频帧回调
     * 
     * 允许外部获取解码后的视频帧数据 (例如用于分析或二次渲染)
     * @param callback 回调函数
     */
    void SetFrameCallback(FrameCallback callback);

private:
    // PIMPL 模式：前置声明实现结构体
    struct Impl;
    std::unique_ptr<Impl> pImpl; ///< 指向实现的指针
};
