### 2. 通信层：高性能接入网关 (Go) - 功能进度表

需要安装Python依赖：pip install websocket-client

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
