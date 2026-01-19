package gateway

import (
	// "log"
	// "sync"
	// "time" // 必须引入时间包

	// "github.com/gorilla/websocket"
	// 用于构造请求体
	// 用于序列化 JSON
	"bytes"
	"context" // 新增：Redis 操作需要上下文
	"encoding/json"
	"log" // 用于发送 HTTP 请求
	"net/http"
	"sync"
	"time"

	"github.com/gorilla/websocket"
	"github.com/redis/go-redis/v9" // 新增：Redis 驱动
)

// DeviceSession 包装连接和它的状态
type DeviceSession struct {
	Conn       *websocket.Conn
	LastActive time.Time // 记录最后一次心跳的时间
}

var ctx = context.Background()

// DeviceManager 负责线程安全地管理所有连接
type DeviceManager struct {
	// connections map[string]*websocket.Conn // 核心数据表：ID -> 连接对象
	// 修改：从 map[string]*websocket.Conn 改为 map[string]*DeviceSession
	connections map[string]*DeviceSession
	lock        sync.RWMutex  // 读写锁，防止并发冲突
	rdb         *redis.Client // 新增：Redis 客户端句柄
}

// NewDeviceManager 创建一个空的管理器
func NewDeviceManager() *DeviceManager {
	// --- 新增：初始化 Redis 连接 ---
	rdb := redis.NewClient(&redis.Options{
		Addr:     "localhost:6379", // 你的 Redis 地址
		Password: "",               // 如果没有密码留空
		DB:       0,                // 默认数据库
	})

	// 测试一下 Redis 是否连接成功
	if _, err := rdb.Ping(ctx).Result(); err != nil {
		log.Fatalf("[Redis] 连接失败，请检查 Redis 是否启动: %v", err)
	}
	log.Println("[Redis] 连接成功！")

	m := &DeviceManager{
		connections: make(map[string]*DeviceSession),
		rdb:         rdb, // 赋值给结构体
	}

	go m.KeepAliveManager()
	return m
}

// Register 设备上线：存入 Map
// Register 改为存储 Session
// 修改 Register：在注册成功后发送上线通知
// Register 设备上线
func (m *DeviceManager) Register(deviceID string, conn *websocket.Conn) {
	m.lock.Lock()
	m.connections[deviceID] = &DeviceSession{
		Conn:       conn,
		LastActive: time.Now(),
	}
	m.lock.Unlock()

	log.Printf("[Manager] 设备 %s 注册成功", deviceID)

	// --- 新增：写入 Redis (关键步骤) ---
	// 逻辑：设置 key="device:online:123"，value="1"，过期时间=60秒
	// 如果60秒内没有心跳续命，Redis 会自动删除这个 key，代表设备离线
	err := m.rdb.Set(ctx, "device:online:"+deviceID, "1", 60*time.Second).Err()
	if err != nil {
		log.Printf("[Redis] 写入状态失败: %v", err)
	}

	m.notifyPythonStatus(deviceID, "online")
}

// UpdateActiveTime 收到心跳或消息时调用
func (m *DeviceManager) UpdateActiveTime(deviceID string) {
	m.lock.Lock()
	// 更新内存中的时间（用于 Go 内部快速判断）
	if session, ok := m.connections[deviceID]; ok {
		session.LastActive = time.Now()
	}
	m.lock.Unlock()

	// --- 新增：给 Redis 续命 (高性能核心) ---
	// 每次收到消息，就重置该设备的过期时间为 60 秒
	// 这样只要设备活着，Key 就一直存在
	m.rdb.Expire(ctx, "device:online:"+deviceID, 60*time.Second)
}

// KeepAliveManager 内部巡检
// 虽然 Redis 有自动过期，但 Go 内存里的 WebSocket 连接对象如果不关，会泄露
// 所以这个函数依然需要，用于清理内存
func (m *DeviceManager) KeepAliveManager() {
	ticker := time.NewTicker(10 * time.Second)
	for range ticker.C {
		m.lock.Lock()
		now := time.Now()
		for id, session := range m.connections {
			// 如果内存中显示超过 60 秒没动静（比 Redis 稍长一点，作为兜底）
			if now.Sub(session.LastActive) > 60*time.Second {
				log.Printf("[巡检] 设备 %s 超时，强制断开", id)
				session.Conn.Close()
				delete(m.connections, id)

				// 顺便确保 Redis 里也删了
				m.rdb.Del(ctx, "device:online:"+id)

				// 因为是在锁内操作，我们需要异步发通知，或者把通知移出锁
				// 这里为了简单，暂不调用 notify 以免死锁风险，依靠 Unregister 逻辑最好
				go m.notifyPythonStatus(id, "offline")
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
// Unregister 设备离线
func (m *DeviceManager) Unregister(deviceID string) {
	m.lock.Lock()
	if session, exists := m.connections[deviceID]; exists {
		session.Conn.Close()
		delete(m.connections, deviceID)
		m.lock.Unlock()

		log.Printf("[Manager] 设备 %s 已注销", deviceID)

		// --- 新增：立即从 Redis 删除状态 ---
		m.rdb.Del(ctx, "device:online:"+deviceID)

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

	pythonWebhookURL := "http://127.0.0.1:5000/api/device/status"
	payload := map[string]interface{}{
		"device_id":  deviceID,
		"status":     status,
		"event_time": time.Now().Unix(),
	}
	jsonBytes, _ := json.Marshal(payload)

	go func() {
		// 这里加个超时控制，防止 Python 挂了卡住协程
		client := http.Client{Timeout: 5 * time.Second}
		resp, err := client.Post(pythonWebhookURL, "application/json", bytes.NewBuffer(jsonBytes))
		if err != nil {
			log.Printf("[Webhook] 通知失败: %v", err)
			return
		}
		defer resp.Body.Close()
	}()
}

// CheckAuth 校验设备身份
func (m *DeviceManager) CheckAuth(deviceID, token string) bool {
	if deviceID == "" || token == "" {
		return false
	}

	// 方案：去 Redis 查找 key 为 "auth:ID"，看 value 是不是对应的 token
	// 这样 Python 后端只需要把合法的 token 塞进 Redis，网关就能识别
	savedToken, err := m.rdb.Get(ctx, "auth:"+deviceID).Result()
	if err != nil {
		// 如果 Redis 里没有这个 key，说明没备案，不予通过
		log.Printf("[Auth] 设备 %s 鉴权失败: 未备案", deviceID)
		return false
	}

	return savedToken == token
}
