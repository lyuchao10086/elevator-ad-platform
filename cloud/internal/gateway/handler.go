package gateway

import (
	"bytes"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/aliyun/aliyun-oss-go-sdk/oss"
	"github.com/google/uuid"
	"github.com/gorilla/websocket"
)

// Handler 结构体：包含了这个接口层需要用到的“工具”
type Handler struct {
	Manager  *DeviceManager     // 引用之前在 manager.go 里写的连接管理器
	upgrader websocket.Upgrader // 用于将普通的 HTTP 协议升级为 WebSocket 协议
	bucket   *oss.Bucket
}

// NewHandler 是一个构造函数，方便 main.go 调用来创建一个新的处理器
func NewHandler(m *DeviceManager, bucket *oss.Bucket) *Handler {
	return &Handler{
		Manager: m,
		bucket:  bucket,
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
	ReqID    string          `json:"req_id"`
	TS       int64           `json:"ts"`
	Payload  json.RawMessage `json:"payload"` // 使用 RawMessage 延迟解析具体内容
}
type SnapshotPayload struct {
	Format     string `json:"format"`     // jpg / png
	Quality    int    `json:"quality"`    // 压缩质量
	Resolution string `json:"resolution"` // 1920x1080
	Data       string `json:"data"`       // Base64 图片数据
}

// 2. 面向电梯端的 WebSocket 接口
// 对应文档：func HandleHandshake(conn Connection)
func (h *Handler) HandleWebsocket(w http.ResponseWriter, r *http.Request) {
	// 1. 获取参数
	deviceID := r.URL.Query().Get("device_id")
	token := r.URL.Query().Get("token")

	// 2. 调用我们刚才写在 Manager 里的鉴权逻辑
	if !h.Manager.CheckAuth(deviceID, token) {
		log.Printf("[鉴权] 拒绝非法连接: ID=%s, Token=%s", deviceID, token)
		http.Error(w, "Unauthorized", http.StatusUnauthorized) // 返回 401
		return
	}

	// 3. 鉴权通过后的逻辑 (之前的代码保持不变)
	conn, err := h.upgrader.Upgrade(w, r, nil)
	if err != nil {
		log.Print("upgrade:", err)
		return
	}

	h.Manager.Register(deviceID, conn)

	// 进入消息路由循环
	go h.DispatchMessage(deviceID, conn)
}

// 3. 消息分发路由器
// 对应文档：func DispatchMessage(msg []byte)
// 3. 消息分发路由器
// 对应文档：func DispatchMessage(msg []byte)
func (h *Handler) DispatchMessage(deviceID string, conn *websocket.Conn) {
	// 使用 defer 确保函数退出时清理资源
	defer func() {
		log.Printf("[网关] 设备 %s 连接断开，正在清理资源...", deviceID)
		h.Manager.Unregister(deviceID)
		conn.Close()
	}()

	for {
		var msg DeviceMessage
		// 读取客户端发来的 JSON 消息
		if err := conn.ReadJSON(&msg); err != nil {
			// 如果读取失败（如客户端主动关闭或断网），直接跳出循环触发 defer
			break
		}

		// --- 核心修改点：只要收到任何包，就刷新该设备在 Manager 里的活跃时间 ---
		h.Manager.UpdateActiveTime(deviceID)

		// 根据消息类型进行分发
		switch msg.Type {
		case "heartbeat":
			// 响应心跳，维持长连接
			conn.WriteJSON(map[string]string{"type": "pong"})

		case "log":
			// 处理播放日志上报
			h.handleLogReport(deviceID, msg.Payload)

		case "snapshot_response":
			// 处理截图上传逻辑
			h.handleSnapshot(msg)

		default:
			log.Printf("[网关] 收到来自 %s 的未知类型消息: %s", deviceID, msg.Type)
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
		DeviceID string          `json:"device_id"`
		Command  string          `json:"command"` // 如: REBOOT, UPDATE_SCHEDULE
		Data     json.RawMessage `json:"data"`
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
	//告诉python后端状态码
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

// Python / Postman 调用：请求设备截图
func (h *Handler) HandleRemoteSnapshot(w http.ResponseWriter, r *http.Request) {
	deviceID := strings.TrimPrefix(r.URL.Path, "/api/v1/devices/remote/")
	deviceID = strings.TrimSuffix(deviceID, "/snapshot")

	conn, ok := h.Manager.GetConnection(deviceID)
	if !ok {
		http.Error(w, "Device Offline", 404)
		return
	}

	reqID := uuid.New().String()

	// 给设备发截图请求
	conn.WriteJSON(map[string]interface{}{
		"type":   "snapshot_request",
		"req_id": reqID,
		"payload": map[string]interface{}{
			"format":     "jpg",
			"quality":    80,
			"resolution": "1920x1080",
		},
	})

	w.WriteHeader(http.StatusOK)
	w.Write([]byte(`{"req_id":"` + reqID + `"}`))
}

// handleSnapshot 处理电梯端上报的截图凭证
func (h *Handler) handleSnapshot(msg DeviceMessage) {
	// 1.解析payload
	var payload SnapshotPayload
	if err := json.Unmarshal(msg.Payload, &payload); err != nil {
		log.Printf("[snapshot] 解析失败: %v", err)
		return
	}

	// 2. Base64 解码
	imgBytes, err := base64.StdEncoding.DecodeString(payload.Data)
	if err != nil {
		log.Printf("[snapshot] Base64 解码失败: %v", err)
		return
	}

	// 3. 生成 OSS Object Key
	objectKey := fmt.Sprintf(
		"snapshots/%s/%d_%s.jpg",
		msg.DeviceID,
		msg.TS,
		msg.ReqID,
	)

	// 4. 尝试上传 OSS（即使失败也继续）
	ossURL := ""
	if h.bucket != nil {
		err = h.bucket.PutObject(
			objectKey,
			bytes.NewReader(imgBytes),
			oss.ContentType("image/jpeg"),
		)
		if err != nil {
			log.Printf("[snapshot] OSS 上传失败: %v", err)
			// 失败了就给个占位图，保证流程不中断
			ossURL = "https://via.placeholder.com/150.jpg"
		} else {
			// 上传成功，拼真实 URL
			ossURL = fmt.Sprintf(
				"https://%s.%s/%s",
				os.Getenv("OSS_BUCKET"),
				os.Getenv("OSS_ENDPOINT"),
				objectKey,
			)
		}
	} else {
		// 如果根本没初始化 OSS，直接给假地址
		log.Printf("[snapshot] OSS 未初始化，跳过上传")
		ossURL = "https://via.placeholder.com/150.jpg"
	}

	log.Printf("[snapshot] 流程继续，准备回调 Python. URL: %s", ossURL)

	// 5. 【关键修改点】调用 NotifyPython (注意首字母大写，匹配 manager.go 里的定义)
	h.Manager.NotifyPython(msg.DeviceID, msg.ReqID, ossURL)
}

// GetStats 供仪表盘调用，获取当前在线统计
func (h *Handler) GetStats(w http.ResponseWriter, r *http.Request) {
	// 1. 从 Redis 模糊查询所有在线 Key
	// 注意：ctx 需要你在文件开头定义 var ctx = context.Background()
	var keys []string
	if h.Manager.rdb != nil {
		k, _ := h.Manager.rdb.Keys(ctx, "device:online:*").Result()
		keys = k
	} else {
		log.Printf("[GetStats] Redis 未连接，返回空在线列表")
		keys = []string{}
	}

	// 2. 构造返回数据
	stats := map[string]interface{}{
		"online_count": len(keys),
		"devices":      keys,
		"server_time":  time.Now().Format("15:04:05"),
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(stats)
}
