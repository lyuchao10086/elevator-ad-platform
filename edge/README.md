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
*   **数据自动同步**：具备后台同步线程，每分钟自动从网关拉取最新的广告素材元数据和排期策略。
*   **本地持久化**：使用 SQLite 存储排期数据和播放日志，启动时保留历史数据，支持断电恢复。
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

### 1. 编译项目（Linux/macOS）

```bash
mkdir build
cd build
cmake ..
make
```

### 1b. 编译项目（Windows，使用 vcpkg）

- 依赖安装（已安装可跳过）
  - vcpkg: D:\vcpkg
  - 安装库: ffmpeg、sdl2、sqlite3、pkgconf、nlohmann-json
- 生成与编译

```powershell
cd d:\D huancun\elevator-ad-platform\edge
cmake -S . -B winbuild `
  -DCMAKE_TOOLCHAIN_FILE=D:\vcpkg\scripts\buildsystems\vcpkg.cmake `
  -DCMAKE_PREFIX_PATH=D:\vcpkg\installed\x64-windows `
  -DPKG_CONFIG_EXECUTABLE=D:\vcpkg\installed\x64-windows\tools\pkgconf\pkgconf.exe
cmake --build winbuild --config Release
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

### 4. 运行播放器（Linux/macOS）

```bash
./build/edge
```

### 4b. 运行播放器（Windows）

```powershell
cd d:\D huancun\elevator-ad-platform\edge
chcp 65001
.\winbuild\Release\edge.exe .\config.json
```

提示：
- 若中文日志有乱码：执行 chcp 65001（UTF-8）
- 若窗口无法创建：Windows 默认渲染驱动为 Direct3D（代码已设置），请确保 GPU/驱动可用

## 模块设计

### 1. EdgeManager (核心控制器)
- **职责**: 负责系统的生命周期管理，协调各个模块工作。
- **关键方法**:
    - `init()`: 初始化配置、数据库、网络和 SDL。
    - `run()`: 主循环，负责计算下一个播放任务 (`getNextAsset`) 并调度播放。
    - `syncAds()`, `syncSchedule()`: 从网关拉取最新数据并同步到本地数据库。
    - `syncLoop()`: 后台线程，每 60 秒触发一次 `syncAds` 和 `syncSchedule`。
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
    - `fetchAds()`, `fetchSchedule()`: 通过 HTTP GET 请求从网关拉取最新数据。
    - `startGatewayConnection(...)`: 启动网关 WebSocket 长连接线程，发送心跳和日志。
    - `stopGatewayConnection()`: 安全停止所有网络连接。

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
1. **同步流程**: `EdgeManager::syncLoop()` -> `EdgeManager::syncAds()`/`syncSchedule()` -> `NetworkClient::fetchAds()`/`fetchSchedule()` -> `Database::execute()` (REPLACE INTO).
2. **播放流程**: `EdgeManager::run()` -> `EdgeManager::getNextAsset()` -> `Database::query()` (查询 schedule 表) -> `VideoPlayer::Load()` -> `VideoPlayer::Play()`.
3. **日志流程**: `EdgeManager::recordPlayEnd()` -> `Database::execute()` (写入 log 表) -> `NetworkClient` (后台线程读取 log 表并上报) -> `EdgeManager::updateLogStatus()` (更新 uploaded=1).

### 网络接口 (HTTP & WebSocket)
- **数据同步 (HTTP GET)**:
    - 获取广告素材: `GET /api/ads`
    - 获取排期策略: `GET /api/schedule`
- **同步结果汇报 (HTTP POST)**:
    - 接口路径: `/api/sync/report`
    - 请求体: `{"type": "ads|schedule", "status": "success|failed", "detail": "...", "timestamp": 123456789}`
- **设备长连接 (WebSocket)**:
    - 连接地址：`ws://<gateway-host>:<port>/ws?device_id=<ID>&token=<TOKEN>`
    - 心跳包：`{"type": "heartbeat", "payload": "ping"}`
    - 日志包：`{"type": "log", "payload": [ ... ]}`
- **指令下发与回包（兼容两种风格）**:
  - 截图下发（二选一）：
    - `{"type":"snapshot_request","req_id":"<uuid>"}` 或
    - `{"type":"command","payload":"SNAPSHOT","cmd_id":"<uuid>"}`
  - 截图回包：
    - `{"type":"snapshot_response","device_id":"<id>","req_id":"<uuid>","ts":<sec>,"payload":{"format":"bmp|jpg","data":"<base64>"}}`
  - 通用命令下发（示例：调整音量）：
    - `{"type":"command","payload":"SET_VOLUME","cmd_id":"<uuid>","data":{"volume":60,"mute":false}}`
  - 通用命令回包：
    - `{"type":"command_response","device_id":"<id>","req_id":"<uuid>","ts":<sec>,"payload":{"cmd_id":"<uuid>","status":"success","result":"set_volume:60|mute:0"}}`
  - 重启设备（软重启）：
    - 下发：`{"type":"command","payload":"REBOOT","cmd_id":"<uuid>"}`
    - 回包：`{"type":"command_response", ... "result":"reboot_ok"}`
    - 行为：设备断开网关、关闭窗口、重新初始化并再次上线（不退出进程）

### Python 辅助联调
- HTTP 触发远程截图（Go 网关提供）：`GET /api/v1/devices/remote/{device_id}/snapshot`
- 通用命令下发（Go 网关提供）：`POST /api/send`，Body: `{"device_id": "...", "command": "SET_VOLUME", "data": {...}}`
- 回调示例与触发脚本参考：[tools/push_to_gateway.py](../tools/push_to_gateway.py)

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

## 播放引擎快速上手（给引擎同学）
- 渲染线程模型
  - 解码线程：`VideoPlayer::DecodeThreadFunc()` 负责生产 YUV 帧（队列 MAX=10）
  - 渲染在主线程：循环调用 `VideoPlayer::Update()`，处理 SDL 事件并刷新纹理
- 媒体加载与播放
  - `Load(path, duration_ms)`：初始化解码器；视频忽略 duration_ms，图片尊重（默认 3000ms）
  - `Play()`：创建/复用 SDL 窗口并启动解码线程
  - `Update()`：`SDL_UpdateYUVTexture + SDL_RenderPresent`，含简单帧率控制
- 渲染驱动选择
  - Windows：`SDL_HINT_RENDER_DRIVER=direct3d`
  - 其他平台：`opengl`
- 截图接口
  - `CaptureSnapshotBMP(filepath)`：读取 Renderer 输出并保存 BMP，供远程截图回包
- 事件与退出
  - SDL_QUIT：EdgeManager 捕获后优雅退出（或软重启）
  - REBOOT 指令：软重启，不退出进程
- 常见问题
  - 中文日志乱码：PowerShell 执行 `chcp 65001`
  - 窗口一闪而过：检查资源路径与 `config.json`；确保在 `edge` 目录运行或显式传入配置路径
  - OpenGL 渲染异常（Windows）：已切换为 Direct3D，若仍异常请确认显卡驱动
