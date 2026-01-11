package gateway

import (
	"sync"

	"github.com/gorilla/websocket"
)

// DeviceManager 负责线程安全地管理所有连接
type DeviceManager struct {
	connections map[string]*websocket.Conn // 核心数据表：ID -> 连接对象
	lock        sync.RWMutex               // 读写锁，防止并发冲突
}

// NewDeviceManager 创建一个空的管理器
func NewDeviceManager() *DeviceManager {
	return &DeviceManager{
		connections: make(map[string]*websocket.Conn),
	}
}

// Register 设备上线：存入 Map
func (m *DeviceManager) Register(deviceID string, conn *websocket.Conn) {
	m.lock.Lock()
	defer m.lock.Unlock()
	m.connections[deviceID] = conn
}

// Unregister 设备离线：从 Map 删除
func (m *DeviceManager) Unregister(deviceID string) {
	m.lock.Lock()
	defer m.lock.Unlock()
	// 为了防止删错，实际工程中通常还会对比 conn 对象，这里简化处理
	delete(m.connections, deviceID)
}

// GetConnection 查找设备：给 Python 发指令用
func (m *DeviceManager) GetConnection(deviceID string) (*websocket.Conn, bool) {
	m.lock.RLock()
	defer m.lock.RUnlock()
	conn, exists := m.connections[deviceID]
	return conn, exists
}
