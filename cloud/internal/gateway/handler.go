package gateway

import (
	"encoding/json"

	"log"
	"net/http"

	"github.com/gorilla/websocket"
)

// Handler 结构体：包含了这个接口层需要用到的“工具”
type Handler struct {
	Manager  *DeviceManager     // 引用之前在 manager.go 里写的连接管理器
	upgrader websocket.Upgrader // 用于将普通的 HTTP 协议升级为 WebSocket 协议
}

// NewHandler 是一个构造函数，方便 main.go 调用来创建一个新的处理器
func NewHandler(m *DeviceManager) *Handler {
	return &Handler{
		Manager: m,
		upgrader: websocket.Upgrader{
			// 解决跨域问题，允许所有来源的连接（测试环境常用）
			CheckOrigin: func(r *http.Request) bool { return true },
		},
	}
}

// 1. 统一消息协议格式
type DeviceMessage struct {
	Type     string          `json:"type"` // heartbeat, log, snapshot, command
	DeviceID string          `json:"device_id"`
	Payload  json.RawMessage `json:"payload"` // 使用 RawMessage 延迟解析具体内容
}

// 2. 面向电梯端的 WebSocket 接口
// 对应文档：func HandleHandshake(conn Connection)
func (h *Handler) HandleWebsocket(w http.ResponseWriter, r *http.Request) {
	deviceID := r.URL.Query().Get("device_id")
	token := r.URL.Query().Get("token") // 增加鉴权参数

	// 逻辑：验证 Token 合法性 (这里简写)
	if token == "" {
		http.Error(w, "Unauthorized", 401)
		return
	}

	conn, _ := h.upgrader.Upgrade(w, r, nil)
	h.Manager.Register(deviceID, conn)

	// 进入消息路由循环
	go h.DispatchMessage(deviceID, conn)
}

// 3. 消息分发路由器
// 对应文档：func DispatchMessage(msg []byte)
func (h *Handler) DispatchMessage(deviceID string, conn *websocket.Conn) {
	for {
		var msg DeviceMessage
		if err := conn.ReadJSON(&msg); err != nil {
			h.Manager.Unregister(deviceID)
			break
		}

		switch msg.Type {
		case "heartbeat":
			// 更新 KeepAliveManager 状态
			conn.WriteJSON(map[string]string{"type": "pong"})
		case "log":
			// 写入 Kafka 或数据库逻辑
			h.handleLogReport(deviceID, msg.Payload)
		case "snapshot":
			// 上传 OSS 逻辑
			h.handleSnapshot(deviceID, msg.Payload)
		}
	}
}

// 4. 面向 Python 的指令下发接口
// 对应文档：func PushCommand(deviceID string, cmd Command)
func (h *Handler) HandleCommand(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Only POST allowed", 405)
		return
	}

	var req struct {
		DeviceID string `json:"device_id"`
		Command  string `json:"command"` // 如: REBOOT, UPDATE_SCHEDULE
		Data     string `json:"data"`
	}

	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "Bad Request", 400)
		return
	}

	// 查找长连接并推送
	conn, exists := h.Manager.GetConnection(req.DeviceID)
	if !exists {
		http.Error(w, "Device Offline", 404)
		return
	}

	conn.WriteJSON(map[string]interface{}{
		"type":    "command",
		"payload": req.Command,
		"data":    req.Data,
	})

	w.WriteHeader(http.StatusOK)
	// --- 在 handler.go 文件末尾添加以下内容 ---

}

// handleLogReport 处理电梯端上报的播放日志
func (h *Handler) handleLogReport(deviceID string, payload json.RawMessage) {
	// 将原始字节直接转换为字符串，这是最稳妥的做法
	content := string(payload)

	// 使用标准日志输出，方便调试
	log.Printf("[日志上报] 设备 ID: %s, 内容: %s", deviceID, content)
}

// handleSnapshot 处理电梯端上报的截图凭证
func (h *Handler) handleSnapshot(deviceID string, payload json.RawMessage) {
	// 对应文档：截图上传 OSS 逻辑
	log.Printf("[截图上报] 收到设备 %s 的截图，数据大小: %d 字节", deviceID, len(payload))
}
