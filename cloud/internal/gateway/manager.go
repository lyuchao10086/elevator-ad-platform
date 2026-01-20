package gateway

import (
	// "log"
	// "sync"
	// "time" // 必须引入时间包

	// "github.com/gorilla/websocket"
	// 用于构造请求体
	// 用于序列化 JSON
	"bytes"
	"encoding/json"
	"log" // 用于发送 HTTP 请求
	"net/http"
	"os"
	"sync"
	"time"

	"github.com/gorilla/websocket"
)

// DeviceSession 包装连接和它的状态
type DeviceSession struct {
	Conn       *websocket.Conn
	LastActive time.Time // 记录最后一次心跳的时间
}

// DeviceManager 负责线程安全地管理所有连接
type DeviceManager struct {
	// connections map[string]*websocket.Conn // 核心数据表：ID -> 连接对象
	// 修改：从 map[string]*websocket.Conn 改为 map[string]*DeviceSession
	connections map[string]*DeviceSession
	lock        sync.RWMutex // 读写锁，防止并发冲突
}

// NewDeviceManager 创建一个空的管理器
func NewDeviceManager() *DeviceManager {
	m := &DeviceManager{
		connections: make(map[string]*DeviceSession),
	}
	// 在启动管理器时，自动开启掉线巡检协程
	go m.KeepAliveManager()
	return m
}

// Register 设备上线：存入 Map
// Register 改为存储 Session
// 修改 Register：在注册成功后发送上线通知
func (m *DeviceManager) Register(deviceID string, conn *websocket.Conn) {
	m.lock.Lock()
	m.connections[deviceID] = &DeviceSession{
		Conn:       conn,
		LastActive: time.Now(),
	}
	m.lock.Unlock()

	log.Printf("[Manager] 设备 %s 注册成功", deviceID)
	// 触发上线通知
	m.notifyPythonStatus(deviceID, "online")
}

// UpdateActiveTime 每次收到心跳或消息时调用
func (m *DeviceManager) UpdateActiveTime(deviceID string) {
	m.lock.Lock()
	defer m.lock.Unlock()
	if session, ok := m.connections[deviceID]; ok {
		session.LastActive = time.Now()
	}
}

// KeepAliveManager 核心巡检逻辑
func (m *DeviceManager) KeepAliveManager() {
	ticker := time.NewTicker(10 * time.Second) // 每10秒检查一轮
	for range ticker.C {
		m.lock.Lock()
		now := time.Now()
		for id, session := range m.connections {
			// 如果超过30秒没动静
			if now.Sub(session.LastActive) > 30*time.Second {
				log.Printf("[巡检] 设备 %s 超时未响应，强制断开", id)
				session.Conn.Close()
				delete(m.connections, id)

				// 下一步这里要调用 Python 的回调接口：NotifyPythonDeviceOffline(id)
			}
		}
		m.lock.Unlock()
	}
}

// // Unregister 设备离线：从 Map 删除

// func (m *DeviceManager) Unregister(deviceID string) {
// 	m.lock.Lock()
// 	defer m.lock.Unlock()

//		// 检查设备是否存在
//		if session, exists := m.connections[deviceID]; exists {
//			// 1. 关闭底层的 WebSocket 连接
//			session.Conn.Close()
//			// 2. 从内存 map 中移除
//			delete(m.connections, deviceID)
//			log.Printf("[Manager] 设备 %s 已注销并清理资源", deviceID)
//		}
//	}
//
// 修改 Unregister：在注销后发送下线通知
func (m *DeviceManager) Unregister(deviceID string) {
	m.lock.Lock()
	if session, exists := m.connections[deviceID]; exists {
		session.Conn.Close()
		delete(m.connections, deviceID)
		m.lock.Unlock() // 先解锁再发通知

		log.Printf("[Manager] 设备 %s 已注销", deviceID)
		// 触发下线通知
		m.notifyPythonStatus(deviceID, "offline")
	} else {
		m.lock.Unlock()
	}
}

// GetConnection 查找设备：给 Python 发指令用
// 修改之前的 GetConnection，因为它现在的返回类型变了
func (m *DeviceManager) GetConnection(deviceID string) (*websocket.Conn, bool) {
	m.lock.RLock()
	defer m.lock.RUnlock()
	session, exists := m.connections[deviceID]
	if !exists {
		return nil, false
	}
	return session.Conn, true
}

// 核心函数：通知 Python 业务中心设备状态变更
func (m *DeviceManager) notifyPythonStatus(deviceID string, status string) {
	// 这里的 URL 对应 Python 后端的接收接口
	pythonWebhookURL := "http://127.0.0.1:5000/api/device/status"
	//pythonWebhookURL := "https://webhook.site/cbb5670e-dd27-44ca-b97f-8695451e4b5a"

	// 构造发送的消息体
	payload := map[string]interface{}{
		"device_id":  deviceID,
		"status":     status, // "online" 或 "offline"
		"event_time": time.Now().Unix(),
	}

	jsonBytes, _ := json.Marshal(payload)

	// 使用协程异步发送，避免通知延迟卡住网关的正常通信
	go func() {
		resp, err := http.Post(pythonWebhookURL, "application/json", bytes.NewBuffer(jsonBytes))
		if err != nil {
			log.Printf("[Webhook] 无法通知 Python 端设备 %s (%s): %v", deviceID, status, err)
			return
		}
		defer resp.Body.Close()
		log.Printf("[Webhook] 已成功通知 Python 端: 设备 %s 状态变更为 %s", deviceID, status)
	}()
}

// 通知python业务中心截图已生成
func (h *Handler) notifyPython(deviceID, reqID, snapshotURL string) {
	callback := os.Getenv("CONTROL_PLANE_SNAPSHOT_CALLBACK")
	if callback == "" {
		callback = "http://127.0.0.1:5000/api/v1/devices/snapshot/callback"
	}

	body := map[string]string{
		"device_id":    deviceID,
		"req_id":       reqID,
		"snapshot_url": snapshotURL,
	}

	data, err := json.Marshal(body)
	if err != nil {
		log.Printf("[snapshot][callback] JSON 序列化失败: %v", err)
		return
	}

	req, err := http.NewRequest("POST", callback, bytes.NewReader(data))
	if err != nil {
		log.Printf("[snapshot][callback] 创建请求失败: %v", err)
		return
	}
	req.Header.Set("Content-Type", "application/json")

	client := &http.Client{
		Timeout: 5 * time.Second,
	}

	resp, err := client.Do(req)
	if err != nil {
		log.Printf("[snapshot][callback] 回调 Python 失败: %v", err)
		return
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		log.Printf(
			"[snapshot][callback] Python 返回非 200: %d",
			resp.StatusCode,
		)
		return
	}

	log.Printf(
		"[snapshot][callback] 回调成功 device=%s req=%s",
		deviceID,
		reqID,
	)
}
