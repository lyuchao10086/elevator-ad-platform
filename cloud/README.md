# 2. 通信层：高性能接入网关 (Go) - 功能进度表

需要安装Python依赖：pip install websocket-client

## 1. 在 cloud 目录下初始化
go mod init elevator_project

## 2. 安装 Redis 驱动
go get github.com/redis/go-redis/v9

## 3. 安装 WebSocket 驱动
go get github.com/gorilla/websocket

## 4. 自动整理（这一步会扫描你的代码并确认依赖）
go mod tidy

## 5. 测试
* 启动redis-server.exe
* 在 redis-cli 中备案 手动存入一个测试 Token：
设置设备 ELEVATOR_001 的合法 token 为 secret123

```solidity
#启动redis-cli.exe
set auth:ELEVATOR_001 secret123
```

* 运行main.go
* 运行python test_device.py
* 打开浏览器访问http://127.0.0.1:8080/dashboard

## 6. 进度

#### **A. 连接管理 (Connection Manager)**

* **`func ListenAndServe(port string)`：【已完成】**
* 在 `main.go` 中使用了 `http.ListenAndServe(":8080", nil)`，这已经实现了启动 WebSocket/HTTP 监听的功能。


* **`func HandleHandshake(conn Connection) error`：【已完成】**
* 在 `handler.go` 的 `HandleWebsocket` 方法中，通过 `r.URL.Query().Get` 获取了 `device_id` 和 `token`。
* 代码中包含了对 `token` 是否为空的校验，实现了初步的鉴权与合法性验证（Session 建立）。


* **`func KeepAliveManager()`：【部分完成】**
* **已实现**：在 `DispatchMessage` 的 `switch` 逻辑中，处理了 `type: "heartbeat"` 的消息并返回 `pong`，实现了基础的心跳响应。
* **待完善**：目前还缺少“超时判定”逻辑。即如果设备 30 秒没发心跳，系统还不会自动将其踢下线并通知 Python 端。

---

#### **B. 消息路由 (Message Router)**

* **`func DispatchMessage(msg []byte)`：【已完成】**
* 实现了 `DispatchMessage` 函数，利用 `conn.ReadJSON` 解析端侧发来的包。
* **路由逻辑**：代码中已经通过 `switch msg.Type` 分发了“日志（log）”和“截图（snapshot）”的处理函数。
* **功能填充**：目前的 `handleLogReport` 和 `handleSnapshot` 还是打印日志（Print），尚未真正接入 Kafka、数据库或 OSS。

* **`func PushCommand(deviceID string, cmd Command)`：【已完成】**
* 实现了 `HandleCommand` 接口（对应 `/api/send`），供 Python 后端通过 HTTP 调用。
* **核心逻辑**：该方法能从 `DeviceManager` 的内存中找到对应电梯的 `Connection`，并将指令（如 REBOOT）实时推送到模拟脚本。

---

### 总结与下一步建议

**当前状态**：已经搭建好了系统的“骨架”，实现了**双向通信**的核心链路。现在的代码已经可以支撑 3-5 台模拟设备长时间运行了

**目前代码的局限性（即接下来的开发重点）：**

1. **数据持久化**：目前所有的日志和连接都在内存里，网关一重启就全没了。
2. **通知机制**：当设备掉线时，代码里还缺少一个 `http.Post` 动作去告诉 Python 后端“某某电梯下线了”。
3. **真正的截图处理**：目前只是打印了“收到截图”，还没有把图片字节流写成文件的逻辑。


# 一、核心基础架构（已完成）

## 1. 连接管理层
-  **WebSocket服务器**：监听`:8080`端口，处理设备连接
-  **连接注册/注销**：设备上线/下线自动管理
-  **连接池管理**：使用`map[string]*DeviceSession`存储所有活跃连接
-  **线程安全**：`sync.RWMutex`保证高并发下的数据一致性
-  **关闭**：`defer`机制确保连接关闭和资源清理

## 2. 心跳保活机制
-  **主动心跳**：设备每5秒发送`heartbeat`，网关回复`pong`
-  **超时检测**：10秒巡检一次，30秒无响应判定为离线
-  **活跃时间更新**：收到任何消息都刷新`LastActive`时间戳
-  **自动清理**：超时设备自动断开连接并从内存移除

## 3. 双向通信协议
-  **上行协议**（设备→网关）：
```json
{
  "type": "log/heartbeat/snapshot",
  "device_id": "设备ID",
  "payload": "消息内容"
}
```
-  **下行协议**（网关→设备）：
```json
{
  "type": "command",
  "payload": "指令类型",
  "data": "额外数据"
}
```

## 4. 接口端点
-  **南向接口**：`/ws` - WebSocket长连接，供设备连接
-  **北向接口**：`/api/send` - HTTP RESTful接口，供Python下发指令

# 二、业务功能实现

## 1. 设备状态管理
-  **在线状态跟踪**：实时维护设备连接状态
-  **状态变更通知**：设备上下线自动通知Python后端
-  **连接查找**：支持按设备ID快速查找连接

## 2. 消息路由处理
-  **消息类型分发**：根据`type`字段路由到不同处理器
-  **心跳处理**：维持连接活跃性
-  **日志上报**：接收设备播放日志（当前仅打印）
-  **截图上报**：接收设备截图（当前仅打印）

## 3. 指令下发系统
-  **HTTP接口**：接收Python后端的指令请求
-  **连接检查**：验证设备是否在线
-  **指令转发**：通过WebSocket发送给对应设备
-  **错误处理**：设备离线返回404错误

# 三、运维监控功能

## 1. 日志系统
-  **连接日志**：设备注册、注销、超时断开
-  **消息日志**：收到和发送的消息记录
-  **错误日志**：连接错误、消息解析错误
-  **通知日志**：Python回调发送记录

## 2. 状态通知
-  **异步回调**：使用goroutine异步通知Python后端
-  **状态同步**：实时同步设备在线状态给业务系统
-  **失败容忍**：HTTP通知失败不影响核心功能