# Edge Computing Player

这是一个基于 C++17 开发的边缘计算广告播放器项目。它设计用于在终端设备（如电梯广告机、商场大屏）上运行，能够根据预设的排期策略自动播放视频广告，支持插播、定投、轮播等多种模式，并具备日志上报和远程控制功能。

## 目录

- [项目简介](#项目简介)
- [核心特性](#核心特性)
- [环境依赖](#环境依赖)
- [编译与运行](#编译与运行)
- [模块设计](#模块设计)
- [数据库设计](#数据库设计)
- [接口说明](#接口说明)
- [配置说明](#配置说明)

## 项目简介

本项目采用模块化设计，核心逻辑由 `EdgeManager` 统一调度，底层使用 `FFmpeg` 进行视频解码，`SDL2` 进行渲染，`SQLite3` 进行本地数据持久化，并使用 `cpp-httplib` 实现 WebSocket/HTTP 网络通信。

## 核心特性

*   **多模式播放**：支持时间段轮播、定点插播、紧急插播等多种播放策略。
*   **离线运行**：所有排期和素材均本地存储，网络断开不影响播放。
*   **本地持久化**：使用 SQLite 存储排期数据和播放日志，支持事务处理。
*   **日志上报**：支持 WebSocket 实时上报播放日志，具备断网重连和本地缓存机制。
*   **远程控制**：支持通过 WebSocket 网关接收远程指令（如更新排期、截屏等）。
*   **自动维护**：具备磁盘空间监控和 LRU 清理机制。

## 环境依赖

*   **编译器**: 支持 C++17 的编译器 (GCC/Clang/MSVC)
*   **构建工具**: CMake >= 3.10
*   **第三方库**:
    *   `ffmpeg` (libavcodec, libavformat, libswscale, libavutil)
    *   `sdl2`
    *   `sqlite3`
    *   `nlohmann_json` (JSON 解析)
    *   `cpp-httplib` (网络通信，需配合 OpenSSL)
    *   `openssl` (可选，用于 HTTPS/WSS)

## 编译与运行

### 1. 编译项目

```bash
mkdir build
cd build
cmake ..
make
```

### 2. 准备资源

确保项目根目录下有 `resources` 目录，并包含以下结构：
```
resources/
├── ads/                  # 存放视频素材文件
├── edge.db               # SQLite 数据库 (自动生成)
├── config.json           # 主配置文件
├── ads.json              # 广告素材元数据
└── schedule.json         # 排期策略文件
```

### 3. 启动 Mock 网关 (可选)

用于本地测试日志上报和心跳功能。

```bash
python3 mock_gateway.py
```

### 4. 运行播放器

```bash
./build/edge
```

## 模块设计

### 1. EdgeManager (核心控制器)
- **职责**: 负责系统的生命周期管理，协调各个模块工作。
- **关键方法**:
    - `init()`: 初始化配置、数据库、网络和 SDL。
    - `run()`: 主循环，负责计算下一个播放任务 (`getNextAsset`) 并调度播放。
    - `syncAds()`, `syncSchedule()`: 同步本地 JSON 配置文件到数据库。
    - `printInfo()`: 统一日志输出接口。
    - `cleanupStorage()`: 磁盘空间清理。

### 2. VideoPlayer (播放引擎)
- **职责**: 封装 FFmpeg 和 SDL2，提供简单的播放接口。
- **关键方法**:
    - `Load(path)`: 加载视频文件，初始化解码器。
    - `Play()`: 启动解码线程。
    - `Update()`: 渲染当前帧 (需在主线程调用)。
    - `Stop()`: 停止播放并释放资源。

### 3. NetworkClient (网络客户端)
- **职责**: 处理与云端的通信。
- **关键方法**:
    - `start(logProvider, ...)`: 启动日志上报线程。
    - `startGatewayConnection(...)`: 启动网关长连接线程，发送心跳。

### 4. Database (数据层)
- **职责**: SQLite3 的 RAII 封装。
- **关键方法**: `execute()`, `query()`, `beginTransaction()`, `commit()`, `rollback()`.

## 数据库设计

系统启动时会自动创建 `resources/edge.db`，包含以下核心表：

### 1. log (播放日志)
记录每次播放的详细信息。
| 字段 | 类型 | 说明 |
| :--- | :--- | :--- |
| log_id | TEXT | UUID 主键 |
| device_id | TEXT | 设备 ID |
| ad_id | TEXT | 广告 ID |
| start_time | TIMESTAMP | 开始播放时间 |
| end_time | TIMESTAMP | 结束播放时间 |
| duration_ms | INT | 播放时长 (毫秒) |
| uploaded | INTEGER | 上报状态 (0:未上传, 1:已上传) |

### 2. advertisement (素材库)
| 字段 | 类型 | 说明 |
| :--- | :--- | :--- |
| ad_id | TEXT | 广告 ID |
| filename | TEXT | 文件名 |
| last_played_time | INTEGER | 最后播放时间 (用于 LRU 清理) |

### 3. schedule_timeslot (时段排期)
| 字段 | 类型 | 说明 |
| :--- | :--- | :--- |
| slot_id | INTEGER | 时段 ID |
| time_range | TEXT | 时间范围 (e.g. "08:00:00-22:00:00") |
| playlist | TEXT | 播放列表 JSON 数组 |
| priority | INTEGER | 优先级 |

### 4. schedule_interrupt (插播策略)
| 字段 | 类型 | 说明 |
| :--- | :--- | :--- |
| trigger_type | TEXT | 触发类型 (e.g. "count", "time") |
| status | INTEGER | 状态 (0:未播放, 1:已播放) |

## 接口说明

### 内部接口调用关系
1. **播放流程**: `EdgeManager::run()` -> `EdgeManager::getNextAsset()` -> `Database::query()` (查询 schedule 表) -> `VideoPlayer::Load()` -> `VideoPlayer::Play()`.
2. **日志流程**: `EdgeManager::recordPlayEnd()` -> `Database::execute()` (写入 log 表) -> `NetworkClient` (后台线程读取 log 表并上报) -> `EdgeManager::updateLogStatus()` (更新 uploaded=1).

### 网络接口 (WebSocket)
- **心跳包**: `{"id": "DEVICE_001", "token": "..."}`
- **日志包**: `{"id": "DEVICE_001", "token": "...", "logs": [...]}`

## 配置说明

`config.json` 示例：
```json
{
    "device_id": "ELEV_001",
    "token": "auth_token_123",
    "resources_dir": "resources/",
    "db_path": "resources/edge.db",
    "ads_config_path": "resources/ads.json",
    "schedule_config_path": "resources/schedule.json",
    "cloud_api_url": "ws://127.0.0.1:8080/",
    "gateway_ws_url": "ws://127.0.0.1:8080/"
}
```
