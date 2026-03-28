#ifndef EDGE_MANAGER_HPP
#define EDGE_MANAGER_HPP

/**
 * @file EdgeManager.hpp
 * @brief 边缘计算节点核心管理器
 * @author Trae AI
 * @date 2026-03-05
 * 
 * 该文件定义了 EdgeManager 类，它是整个边缘端程序的核心控制器。
 * 负责系统的初始化、配置加载、数据库管理、任务调度、播放控制以及日志记录。
 */

#pragma once

#include "Config.hpp"
#include "Database.hpp"
#include "PlayItem.hpp"
#include "VideoPlayer.hpp"
#include "NetworkClient.hpp" // 引入 NetworkClient
#include "Log.hpp" 
#include <nlohmann/json.hpp>
#include <string>
#include <memory>
#include <vector>
#include <thread>
#include <atomic>

using json = nlohmann::json;

/**
 * @class EdgeManager
 * @brief 边缘端核心管理类
 * 
 * EdgeManager 采用单例模式或作为主程序的唯一实例存在。
 * 它协调各个子模块（数据库、播放器、调度器）的工作。
 */
class EdgeManager {
public:
    /**
     * @brief 构造函数
     */
    EdgeManager();

    /**
     * @brief 析构函数
     */
    ~EdgeManager();

    /**
     * @brief 初始化管理器
     * 
     * 执行系统的启动流程，包括：
     * 1. 加载配置文件
     * 2. 初始化数据库连接
     * 3. 加载初始数据 (广告素材、排期策略)
     * 4. 执行磁盘清理
     * 5. 初始化播放器子系统
     * 
     * @param configPath 配置文件路径 (JSON格式)
     * @return true 初始化成功
     * @return false 初始化失败 (如配置错误、数据库连接失败等)
     */
    bool init(const std::string& configPath, bool isPlayerMode = false);
    
    /**
     * @brief 启动主运行循环
     * 
     * 这是一个阻塞方法，包含系统的核心业务逻辑循环：
     * 1. 根据策略生成当前时刻的播放列表
     * 2. 调度播放任务
     * 3. 调用 VideoPlayer 进行媒体播放
     * 4. 监控播放状态和窗口事件
     * 5. 更新播放统计数据
     * 
     * 该方法直到程序接收到退出信号或窗口关闭才会返回。
     */
    void run();

    /**
     * @brief 获取当前系统配置
     * @return const Config& 配置对象的只读引用
     */
    const Config& getConfig() const;

    /**
     * @brief 初始化数据库
     * 
     * 建立 SQLite 数据库连接。
     * 如果是首次运行或需要重置，会先删除旧表，然后创建最新的表结构。
     * 包含的表：advertisement, schedule, schedule_interrupt, schedule_timeslot, log 等。
     * 
     * @return true 成功
     * @return false 失败
     */
    bool initDatabase();

    /**
     * @brief 同步广告素材数据 (从文件)
     * 
     * 读取 Ads.json 配置文件，解析广告元数据并存入 advertisement 表。
     * @return true 成功
     * @return false 失败
     */
    bool syncAds();

    /**
     * @brief 同步广告素材数据 (从 JSON 对象)
     * 
     * 解析广告 JSON 数据并存入 advertisement 表。
     * @param adsJson 包含 "ads" 数组的 JSON 对象
     * @return true 成功
     * @return false 失败
     */
    bool loadAds(const json& adsJson);

    /**
     * @brief 同步排期策略数据 (从文件)
     * 
     * 读取 Schedule.json 配置文件，解析排期策略并存入 schedule 相关表。
     * @return true 成功
     * @return false 失败
     */
    bool syncSchedule();

    /**
     * @brief 同步排期策略数据 (从 JSON 对象)
     * 
     * 解析排期 JSON 数据并存入 schedule 相关表。
     * @param scheduleJson 排期策略 JSON 对象
     * @return true 成功
     * @return false 失败
     */
    bool loadSchedule(const json& scheduleJson);

    /**
     * @brief 获取下一个要播放的素材
     * 
     * 根据当前时间、优先级算法（插播 > 定投 > 轮播），计算下一个播放项。
     * @return std::unique_ptr<PlayItem> 下一个播放项，如果没有则返回 nullptr
     */
    std::unique_ptr<PlayItem> getNextAsset();

    /**
     * @brief 初始化播放列表
     * 
     * 检查当前时间段的排期配置，验证所需素材是否存在。
     * 如果关键素材缺失，可能需要触发下载或报警。
     * 
     * @return true 初始化成功 (素材就绪)
     * @return false 初始化失败 (关键素材缺失)
     */
    bool initPlaylist();

    /**
     * @brief 清理存储空间 (LRU)
     * 
     * 检查资源目录占用的总空间，如果超过阈值 (10GB)，
     * 则按照 last_played_time 从旧到新删除文件，直到占用空间低于阈值。
     */
    void cleanupStorage();

    /**
     * @brief 日志级别定义
     */
    enum class LogLevel {
        INFO,    ///< 普通信息
        WARNING, ///< 警告信息
        ERROR    ///< 错误信息
    };

    /**
     * @brief 记录播放日志 (详细)
     * 
     * @param adId 广告 ID
     * @param adFileName 广告文件名
     * @param startTime 开始时间戳
     * @param endTime 结束时间戳
     * @param durationMs 播放时长(ms)
     * @param statusCode 状态码 (200/404/500)
     * @param statusMsg 状态信息
     */
    void log(const std::string& adId, const std::string& adFileName, long long startTime, long long endTime, int durationMs, int statusCode, const std::string& statusMsg);

    /**
     * @brief 批量更新日志上传状态
     * 
     * @param logIds 已上传的日志 ID 列表
     * @param status 状态值 (1: 已上传)
     */
    void updateLogStatus(const std::vector<std::string>& logIds, int status);

    /**
     * @brief 记录日志 (系统日志)
     * 
     * 双向日志输出：
     * 1. 格式化输出到控制台 (stdout/stderr)，带颜色和线程ID
     * 
     * @param level 日志级别
     * @param message 日志内容
     */
    void printInfo(LogLevel level, const std::string& message);

    /**
     * @brief 获取最近的日志记录
     * 
     * 查询 log 表，返回最新的 n 条记录。
     * @param limit 获取的条数 (默认 100)
     * @return json 包含 Log 对象数组的 JSON
     */
    json getLogs(int limit = 100);

private:
    Config config_;                 ///< 系统配置对象
    bool is_initialized_;           ///< 初始化状态标记
    std::unique_ptr<Database> db_;  ///< 数据库实例指针
    std::unique_ptr<VideoPlayer> player_; ///< 视频播放器实例指针
    std::unique_ptr<NetworkClient> network_; ///< 网络客户端实例指针
    int current_volume_ = 60;
    bool current_mute_ = false;
    bool is_player_mode_ = false;
    std::atomic<bool> should_exit_{false};
    std::atomic<bool> should_soft_reboot_{false};

    // 同步线程
    std::thread syncThread_;
    std::atomic<bool> syncRunning_{false};
    void syncLoop();

    // 守护进程心跳线程
    std::thread watchdogHeartbeatThread_;
    void watchdogHeartbeatLoop();

    // 守护进程命令监听线程
    std::thread watchdogCommandThread_;
    void watchdogCommandLoop();

    // 轮播索引 (用于 getNextAsset 轮询 timeslot 中的列表)
    size_t current_playlist_index_ = 0;
    // 上次播放的 timeslot ID，用于重置索引
    int last_timeslot_id_ = -1;

    /**
     * @brief 检查当前时间是否在指定的时间段内
     * 
     * @param timeRange 时间段字符串，格式为 "HH:MM:SS-HH:MM:SS" (例如 "08:00:00-10:00:00")
     * @return true 当前时间在范围内
     * @return false 当前时间不在范围内或格式解析错误
     */
    bool isTimeInSlot(const std::string& timeRange);
    
    /**
     * @brief 获取当前的系统时间字符串
     * @return std::string 格式为 "HH:MM:SS"
     */
    std::string getCurrentTimeStr();

    /**
     * @brief 加载配置文件
     * 
     * 读取并解析 config.json 文件
     * @param configPath 文件路径
     * @return true 成功
     * @return false 失败
     */
    bool loadConfig(const std::string& configPath);

    // --- 内部辅助方法 (重构新增) ---

    /**
     * @brief 记录播放开始状态
     * 
     * 将当前播放任务写入 playlist 表，用于断电恢复和实时监控。
     * @param item 播放项
     */
    void recordPlayStart(const PlayItem& item);

    /**
     * @brief 记录播放结束状态
     * 
     * 生成详细的播放日志并写入 log 表。
     * 同时更新素材的 last_played_time 和插播任务状态。
     * 
     * @param item 播放项
     * @param startTime 开始时间戳
     * @param durationMs 实际播放时长
     * @param statusCode 状态码
     */
    void recordPlayEnd(const PlayItem& item, long long startTime, int durationMs, int statusCode = 200);

    /**
     * @brief 处理空闲等待
     * 
     * 当没有可播放内容时，执行分段休眠并响应退出信号。
     * @return true 继续运行
     * @return false 收到退出信号，应终止主循环
     */
    bool waitForPlaybackOrStop();

    /**
     * @brief 处理来自云端的指令
     * 
     * @param msg 接收到的云端消息 (JSON)
     * @param send 回调函数，用于发送回包
     */
    void handleCloudCommand(const json& msg, std::function<void(const json&)> send);
};

#endif // EDGE_MANAGER_HPP
