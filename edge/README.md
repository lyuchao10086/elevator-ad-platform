# Edge Computing Player (边缘计算播放器)

这是一个基于 C++17 开发的高可靠边缘计算广告播放器。该系统专为电梯广告机、商场大屏等终端设备设计，采用“守护进程 + 播放器进程”的双进程架构，确保系统在无人值守环境下的 7x24 小时稳定运行。

## 核心架构

系统由两个主要部分组成：

1.  **Watchdog (守护进程)**：
    *   **生命周期管理**：负责拉起播放器进程，并在其崩溃或假死时自动重启。
    *   **云端通信**：接管 WebSocket 长连接，处理心跳、日志上报和云端指令。
    *   **本地监控**：通过 UDP 心跳实时监控播放器主循环状态。
    *   **指令中转**：将云端指令（如截图、音量控制）通过本地 IPC 转发给播放器。

2.  **EdgeManager (播放器进程)**：
    *   **音视频引擎**：基于 FFmpeg 解码和 SDL2 渲染。
    *   **智能调度**：支持插播、轮播、定投等多种播放策略。
    *   **数据同步**：定期拉取最新的广告素材和排期表。
    *   **本地存储**：使用 SQLite 记录详细的播放日志。

## 技术栈

*   **语言**: C++17
*   **框架**: FFmpeg, SDL2, SQLite3, cpp-httplib, nlohmann-json
*   **IPC**: UDP (本地心跳与命令中转)

## 快速开始

### 1. 编译项目

```bash
mkdir build
cd build
cmake ..
make
```

### 2. 运行

**推荐方式（守护进程模式）：**
```bash
./build/edge --watchdog ./config.json
```
守护进程会自动拉起播放器，并监控其运行状态。

**调试方式（仅启动播放器）：**
```bash
./build/edge ./config.json
```

## 目录结构

*   `src/`: 源代码文件
    *   `Watchdog.cpp`: 守护进程核心实现
    *   `EdgeManager.cpp`: 播放业务逻辑
    *   `VideoPlayer.cpp`: FFmpeg 播放引擎
    *   `NetworkClient.cpp`: 网络通信模块
*   `include/`: 头文件
*   `resources/`: 存放素材、排期、配置和数据库文件

## 监控与日志

*   **本地心跳**: 播放器每 5s 向守护进程发送一次 UDP 包。
*   **故障自愈**: 
    *   若播放器崩溃，守护进程立即重启。
    *   若播放器假死（30s 无心跳），守护进程强制杀死并重启。
*   **日志记录**: 所有故障事件（CRASH, HANG, RESTART）均记录在本地 SQLite 的 `log` 表中，并自动上报云端。

## 远程指令支持

通过云端 WebSocket 下发 JSON 指令：
*   `REBOOT`: 触发播放器软重启。
*   `SNAPSHOT`: 获取当前播放画面截图。
*   `SET_VOLUME`: 远程调节音量。

---
*Developed by Trae AI Pair Programming.*
