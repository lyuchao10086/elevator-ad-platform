package gateway

import (
	"bytes"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"github.com/aliyun/aliyun-oss-go-sdk/oss"
	"github.com/google/uuid"
	"github.com/gorilla/websocket"
	// "github.com/redis/go-redis/v9"
)

// Handler 结构体：包含了这个接口层需要用到的“工具”
type Handler struct {
	Manager  *DeviceManager     // 引用之前在 manager.go 里写的连接管理器
	upgrader websocket.Upgrader // 用于将普通的 HTTP 协议升级为 WebSocket 协议
	bucket   *oss.Bucket
	kafka    *KafkaProducer // ⭐ 新增
}

type deviceBundle struct {
	DeviceID     string                   `json:"device_id"`
	CampaignID   string                   `json:"campaign_id"`
	Version      string                   `json:"version"`
	GeneratedAt  string                   `json:"generated_at"`
	Schedule     map[string]interface{}   `json:"schedule"`
	ScheduleCfg  map[string]interface{}   `json:"schedule_config"`
	EdgeSchedule map[string]interface{}   `json:"edge_schedule"`
	Assets       []map[string]interface{} `json:"assets"`
	ScheduleFmt  string                   `json:"schedule_format"`
}

// NewHandler 是一个构造函数，方便 main.go 调用来创建一个新的处理器
func NewHandler(m *DeviceManager, bucket *oss.Bucket, kafka *KafkaProducer) *Handler {
	return &Handler{
		Manager: m,
		bucket:  bucket,
		kafka:   kafka,
		upgrader: websocket.Upgrader{
			// 解决跨域问题，允许所有来源的连接（测试环境常用）
			CheckOrigin: func(r *http.Request) bool { return true },
		},
	}
}

// 1. 统一消息协议格式
type DeviceMessage struct {
	Type     string          `json:"type"` // heartbeat, log, snapshot_response, command
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
type PlayLogPayload struct {
	LogID      string `json:"log_id"`
	DeviceID   string `json:"device_id"`
	AdID       string `json:"ad_id"`
	AdFileName string `json:"ad_file_name"`

	StartTime  string `json:"start_time"`
	EndTime    string `json:"end_time"`
	DurationMs int64  `json:"duration_ms"`

	StatusCode int    `json:"status_code"`
	StatusMsg  string `json:"status_msg"`

	CreatedAt       int64  `json:"created_at"`
	DeviceIP        string `json:"device_ip"`
	FirmwareVersion string `json:"firmware_version"`
}

// type PlayLogPayload struct {
// 	LogID string `json:"log_id"`
// 	AdID  string `json:"ad_id"`

// 	PlaybackInfo struct {
// 		StartTime  string `json:"start_time"`
// 		EndTime    string `json:"end_time"`
// 		DurationMs int64  `json:"duration_ms"`
// 		StatusCode int    `json:"status_code"`
// 		StatusMsg  string `json:"status_msg"`
// 	} `json:"playback_info"`

// 	SecurityCheck struct {
// 		ExpectedMD5 string `json:"expected_md5"`
// 		ActualMD5   string `json:"actual_md5"`
// 	} `json:"security_check"`

// 	Meta struct {
// 		FirmwareVersion string `json:"firmware_version"`
// 		ClientIP        string `json:"client_ip"`  // 终端可不传，网关兜底
// 		CreatedAt       int64  `json:"created_at"` // 网关填写
// 	} `json:"meta"`
// }

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
	clientIP := getClientIP(r)
	// 3. 鉴权通过后的逻辑 (之前的代码保持不变)
	conn, err := h.upgrader.Upgrade(w, r, nil)
	if err != nil {
		log.Print("upgrade:", err)
		return
	}

	h.Manager.Register(deviceID, conn, clientIP)

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
			h.handleLogReport(conn, msg.Payload)

		case "snapshot_response":
			// 处理截图上传逻辑
			h.handleSnapshot(msg)

		case "command_response":
			// 处理设备对指令的回执，期望 payload 中包含 {"cmd_id":"...","status":"success","result":"..."}
			var data struct {
				CmdID  string `json:"cmd_id"`
				Status string `json:"status"`
				Result string `json:"result"`
			}
			if err := json.Unmarshal(msg.Payload, &data); err != nil {
				log.Printf("[command_response] payload 解析失败: %v", err)
				break
			}
			// 调用 Manager 回调 control-plane
			h.Manager.NotifyCommandCallback(deviceID, data.CmdID, data.Status, data.Result)

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
		CmdID    string          `json:"cmd_id"`
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

	// 将 cmd_id 一并透传给设备，方便设备回报时带回
	conn.WriteJSON(map[string]interface{}{
		"type":    "command",
		"payload": req.Command,
		"data":    req.Data,
		"cmd_id":  req.CmdID,
	})
	//告诉python后端状态码
	w.WriteHeader(http.StatusOK)
	// --- 在 handler.go 文件末尾添加以下内容 ---

}

// handleLogReport 处理电梯端上报的播放日志
func (h *Handler) handleLogReport(conn *websocket.Conn, payload json.RawMessage) {
	var logs []PlayLogPayload

	// 1️⃣ 尝试解析播放日志
	if err := json.Unmarshal(payload, &logs); err != nil {
		log.Printf(
			"[playlog][invalid] err=%v raw=%s",
			err, string(payload),
		)
		// 可以给侧端返回解析失败
		conn.WriteJSON(map[string]interface{}{
			"type":    "log_ack",
			"success": false,
			"message": "invalid payload",
		})
		return
	}
	for i := range logs {
		//获得日志设备ID
		deviceID := logs[i].DeviceID
		// 2️⃣ 网关补充字段(时间、IP)
		logs[i].CreatedAt = time.Now().Unix()
		logs[i].DeviceIP = h.Manager.GetDeviceIP(deviceID)

		// 3️⃣ 运维日志（人能看懂）
		log.Printf(
			"[playlog] device=%s log_id=%s ad_id=%s duration=%d status=%d",
			deviceID,
			logs[i].LogID,
			logs[i].AdID,
			logs[i].DurationMs,
			logs[i].StatusCode,
		)
		// 4️⃣ Kafka 投递
		if h.kafka != nil {

			data, err := json.Marshal(logs[i])
			if err != nil {
				log.Printf("[playlog][marshal_failed] %v", err)
				return
			}

			err = h.kafka.Send(deviceID, data)
			if err != nil {
				log.Printf(
					"[playlog][kafka_failed] device=%s err=%v",
					deviceID, err,
				)
			} else {
				log.Printf(
					"[playlog][kafka_ok] device=%s log_id=%s",
					deviceID,
					logs[i].LogID,
				)
			}
		}
	}
	// ✅ 发送 ACK 给电梯端
	conn.WriteJSON(map[string]interface{}{
		"type":    "log_ack",
		"success": true,
		"count":   len(logs),
		"message": "logs received",
		"ts":      time.Now().Unix(),
	})
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
	var ossURL string
	// 4. 上传 OSS
	if h.bucket == nil {
		// ❗这是配置 / 初始化问题，必须显式打出来
		log.Printf(
			"[snapshot][ERROR] OSS 未初始化 device=%s req=%s",
			msg.DeviceID, msg.ReqID,
		)
		ossURL = "" // 明确失败
	} else {
		err = h.bucket.PutObject(
			objectKey,
			bytes.NewReader(imgBytes),
			oss.ContentType("image/jpeg"),
		)

		if err != nil {
			// ❗上传失败，但不伪装成功
			log.Printf(
				"[snapshot][ERROR] OSS 上传失败 device=%s req=%s key=%s err=%v",
				msg.DeviceID,
				msg.ReqID,
				objectKey,
				err,
			)
			ossURL = ""
		} else {
			//上传成功
			// 使用 SDK 生成签名 URL (过期时间为 1 小时)
			signedURL, err := h.bucket.SignURL(objectKey, oss.HTTPGet, 3600)
			if err != nil {
				log.Printf("[OSS] 生成签名 URL 失败: %v", err)
				return
			}
			ossURL = signedURL
			log.Printf(
				"[snapshot] OSS 上传成功 device=%s req=%s url=%s",
				msg.DeviceID,
				msg.ReqID,
				ossURL,
			)
		}
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

// 获取终端设备IP
func getClientIP(r *http.Request) string {
	if xff := r.Header.Get("X-Forwarded-For"); xff != "" {
		return strings.TrimSpace(strings.Split(xff, ",")[0])
	}
	if xrip := r.Header.Get("X-Real-IP"); xrip != "" {
		return xrip
	}
	host, _, err := net.SplitHostPort(r.RemoteAddr)
	if err != nil {
		return r.RemoteAddr
	}
	return host
}

// Handler 结构体中需要实现这个方法
func (h *Handler) GetDevicePolicy(w http.ResponseWriter, r *http.Request) {
	deviceID, ok := h.validateDeviceRequest(w, r)
	if !ok {
		return
	}
	bundle, err := h.getDeviceBundle(deviceID)
	if err != nil {
		http.Error(w, "Failed to load policy", http.StatusBadGateway)
		return
	}

	policy := bundle.ScheduleCfg
	if len(policy) == 0 {
		policy = bundle.Schedule
	}
	if len(policy) == 0 {
		policy = map[string]interface{}{
			"version":    bundle.Version,
			"playlist":   []map[string]interface{}{},
			"interrupts": []map[string]interface{}{},
		}
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(policy)
}

// GetSchedule 提供端侧兼容接口，返回 edge-schedule 结构
func (h *Handler) GetSchedule(w http.ResponseWriter, r *http.Request) {
	deviceID, ok := h.validateDeviceRequest(w, r)
	if !ok {
		return
	}

	bundle, err := h.getDeviceBundle(deviceID)
	if err != nil {
		http.Error(w, "Failed to load schedule", http.StatusBadGateway)
		return
	}

	schedule := bundle.EdgeSchedule
	if len(schedule) == 0 {
		schedule = bundle.Schedule
	}
	if len(schedule) == 0 {
		http.Error(w, "No schedule available", http.StatusNotFound)
		return
	}
	schedule = normalizeScheduleForEdge(schedule)

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(schedule)
}

func normalizeScheduleForEdge(schedule map[string]interface{}) map[string]interface{} {
	out := make(map[string]interface{}, len(schedule)+3)
	for k, v := range schedule {
		out[k] = v
	}

	if gcRaw, ok := out["global_config"].(map[string]interface{}); ok {
		if _, exists := out["default_volume"]; !exists {
			if v, ok := gcRaw["default_volume"]; ok {
				out["default_volume"] = v
			}
		}
		if _, exists := out["download_retry_count"]; !exists {
			if v, ok := gcRaw["download_retry_count"]; ok {
				out["download_retry_count"] = v
			}
		}
		if _, exists := out["report_interval_sec"]; !exists {
			if v, ok := gcRaw["report_interval_sec"]; ok {
				out["report_interval_sec"] = v
			}
		}
	}

	if _, exists := out["default_volume"]; !exists {
		out["default_volume"] = 60
	}
	if _, exists := out["download_retry_count"]; !exists {
		out["download_retry_count"] = 3
	}
	if _, exists := out["report_interval_sec"]; !exists {
		out["report_interval_sec"] = 60
	}

	return out
}

// GetAds 提供端侧兼容接口，返回 {"ads": [...]} 结构
func (h *Handler) GetAds(w http.ResponseWriter, r *http.Request) {
	deviceID, ok := h.validateDeviceRequest(w, r)
	if !ok {
		return
	}

	bundle, err := h.getDeviceBundle(deviceID)
	if err != nil {
		http.Error(w, "Failed to load ads", http.StatusBadGateway)
		return
	}

	ads := make([]map[string]interface{}, 0, len(bundle.Assets))
	for _, asset := range bundle.Assets {
		adID, _ := asset["id"].(string)
		t, _ := asset["type"].(string)
		filename, _ := asset["filename"].(string)
		md5, _ := asset["md5"].(string)
		duration := toInt(asset["duration"])
		bytes := toInt64(asset["size_bytes"])

		if adID == "" || filename == "" {
			continue
		}

		if _, err := h.ensureAssetCached(asset); err != nil {
			log.Printf("[material][cache] failed ad_id=%s filename=%s err=%v", adID, filename, err)
		}

		ads = append(ads, map[string]interface{}{
			"ad_id":    adID,
			"type":     t,
			"filename": filename,
			"md5":      md5,
			"duration": duration,
			"bytes":    bytes,
			"url":      fmt.Sprintf("/api/material/file?device_id=%s&ad_id=%s", deviceID, adID),
		})
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"version": bundle.Version,
		"ads":     ads,
	})
}

// GetMaterialFile 提供素材文件下载接口，未命中本地缓存时会回源 control-plane 拉取后再返回
func (h *Handler) GetMaterialFile(w http.ResponseWriter, r *http.Request) {
	deviceID, ok := h.validateDeviceRequest(w, r)
	if !ok {
		return
	}

	adID := strings.TrimSpace(r.URL.Query().Get("ad_id"))
	filename := strings.TrimSpace(r.URL.Query().Get("filename"))
	if adID == "" && filename == "" {
		http.Error(w, "Missing ad_id or filename", http.StatusBadRequest)
		return
	}

	bundle, err := h.getDeviceBundle(deviceID)
	if err != nil {
		http.Error(w, "Failed to load bundle", http.StatusBadGateway)
		return
	}

	var found map[string]interface{}
	for _, asset := range bundle.Assets {
		curAdID, _ := asset["id"].(string)
		curFilename, _ := asset["filename"].(string)
		if (adID != "" && curAdID == adID) || (filename != "" && curFilename == filename) {
			found = asset
			break
		}
	}
	if found == nil {
		http.Error(w, "Material not found in device bundle", http.StatusNotFound)
		return
	}

	localPath, err := h.ensureAssetCached(found)
	if err != nil {
		http.Error(w, "Failed to fetch material", http.StatusBadGateway)
		return
	}

	serveName := filepath.Base(localPath)
	w.Header().Set("Content-Type", "application/octet-stream")
	w.Header().Set("Content-Disposition", fmt.Sprintf("attachment; filename=\"%s\"", serveName))
	http.ServeFile(w, r, localPath)
}

func (h *Handler) extractDeviceID(r *http.Request) string {
	deviceID := strings.TrimSpace(r.URL.Query().Get("device_id"))
	if deviceID != "" {
		return deviceID
	}

	deviceID = strings.TrimSpace(r.Header.Get("X-Device-ID"))
	if deviceID != "" {
		return deviceID
	}

	return ""
}

func (h *Handler) extractToken(r *http.Request) string {
	token := strings.TrimSpace(r.URL.Query().Get("token"))
	if token != "" {
		return token
	}

	token = strings.TrimSpace(r.Header.Get("X-Device-Token"))
	if token != "" {
		return token
	}

	auth := strings.TrimSpace(r.Header.Get("Authorization"))
	if strings.HasPrefix(strings.ToLower(auth), "bearer ") {
		return strings.TrimSpace(auth[7:])
	}

	return ""
}

func (h *Handler) validateDeviceRequest(w http.ResponseWriter, r *http.Request) (string, bool) {
	deviceID := h.extractDeviceID(r)
	if deviceID == "" {
		http.Error(w, "Missing device_id", http.StatusBadRequest)
		return "", false
	}
	token := h.extractToken(r)
	if !h.Manager.CheckAuth(deviceID, token) {
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return "", false
	}
	return deviceID, true
}

func gatewayMaterialCacheDir() string {
	dir := strings.TrimSpace(os.Getenv("GATEWAY_MATERIAL_CACHE_DIR"))
	if dir == "" {
		dir = "storage/materials"
	}
	return dir
}

func fileExistsWithSize(path string) bool {
	info, err := os.Stat(path)
	if err != nil {
		return false
	}
	return !info.IsDir() && info.Size() > 0
}

func (h *Handler) ensureAssetCached(asset map[string]interface{}) (string, error) {
	filename, _ := asset["filename"].(string)
	filename = filepath.Base(strings.TrimSpace(filename))
	if filename == "" {
		return "", fmt.Errorf("asset missing filename")
	}

	cacheDir := gatewayMaterialCacheDir()
	if err := os.MkdirAll(cacheDir, 0o755); err != nil {
		return "", err
	}

	localPath := filepath.Join(cacheDir, filename)
	if fileExistsWithSize(localPath) {
		return localPath, nil
	}

	materialID, _ := asset["material_id"].(string)
	downloadURL := ""

	// Prefer upstream direct source URL (for OSS or CDN). Fallback to control-plane file API.
	if u, _ := asset["signed_source_url"].(string); strings.TrimSpace(u) != "" {
		downloadURL = strings.TrimSpace(u)
	}
	if downloadURL == "" {
		u, _ := asset["source_url"].(string)
		downloadURL = strings.TrimSpace(u)
	}
	if downloadURL == "" {
		u, _ := asset["download_url"].(string)
		downloadURL = strings.TrimSpace(u)
	}
	if downloadURL == "" && materialID != "" {
		downloadURL = h.buildMaterialDownloadURL(materialID)
	}
	if downloadURL == "" {
		return "", fmt.Errorf("asset missing download url")
	}

	if err := downloadFileToPath(downloadURL, localPath); err != nil {
		return "", err
	}

	return localPath, nil
}

func (h *Handler) buildMaterialDownloadURL(materialID string) string {
	baseURL := strings.TrimRight(getEnvWithDefault("CONTROL_PLANE_BASE_URL", "http://127.0.0.1:8000"), "/")
	return fmt.Sprintf("%s/api/v1/gateway/materials/%s/file", baseURL, materialID)
}

func downloadFileToPath(url, dstPath string) error {
	client := &http.Client{Timeout: 30 * time.Second}
	resp, err := client.Get(url)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("download status: %d", resp.StatusCode)
	}

	tmpPath := dstPath + ".tmp"
	f, err := os.Create(tmpPath)
	if err != nil {
		return err
	}

	if _, err = io.Copy(f, resp.Body); err != nil {
		f.Close()
		_ = os.Remove(tmpPath)
		return err
	}
	if err = f.Close(); err != nil {
		_ = os.Remove(tmpPath)
		return err
	}

	if err = os.Rename(tmpPath, dstPath); err != nil {
		_ = os.Remove(tmpPath)
		return err
	}

	return nil
}

func bundleCacheTTL() time.Duration {
	v := strings.TrimSpace(os.Getenv("GATEWAY_BUNDLE_CACHE_TTL_SEC"))
	if v == "" {
		return 60 * time.Second
	}
	sec, err := strconv.Atoi(v)
	if err != nil || sec <= 0 {
		return 60 * time.Second
	}
	return time.Duration(sec) * time.Second
}

func bundleCacheKey(deviceID string) string {
	return "device:bundle:" + deviceID
}

func (h *Handler) getDeviceBundle(deviceID string) (*deviceBundle, error) {
	if h.Manager != nil && h.Manager.rdb != nil {
		cached, err := h.Manager.rdb.Get(ctx, bundleCacheKey(deviceID)).Result()
		if err == nil && cached != "" {
			var b deviceBundle
			if json.Unmarshal([]byte(cached), &b) == nil {
				return &b, nil
			}
		}
	}

	b, raw, err := h.fetchBundleFromControlPlane(deviceID)
	if err != nil {
		return nil, err
	}

	if h.Manager != nil && h.Manager.rdb != nil {
		h.Manager.rdb.Set(ctx, bundleCacheKey(deviceID), raw, bundleCacheTTL())
	}

	return b, nil
}

func (h *Handler) fetchBundleFromControlPlane(deviceID string) (*deviceBundle, []byte, error) {
	baseURL := strings.TrimRight(getEnvWithDefault("CONTROL_PLANE_BASE_URL", "http://127.0.0.1:8000"), "/")
	url := fmt.Sprintf("%s/api/v1/gateway/devices/%s/bundle", baseURL, deviceID)

	client := &http.Client{Timeout: 5 * time.Second}
	resp, err := client.Get(url)
	if err != nil {
		return nil, nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, nil, fmt.Errorf("control-plane status: %d", resp.StatusCode)
	}

	var b deviceBundle
	buf := new(bytes.Buffer)
	if _, err := buf.ReadFrom(resp.Body); err != nil {
		return nil, nil, err
	}
	if err := json.Unmarshal(buf.Bytes(), &b); err != nil {
		return nil, nil, err
	}

	return &b, buf.Bytes(), nil
}

func toInt(v interface{}) int {
	switch t := v.(type) {
	case float64:
		return int(t)
	case int:
		return t
	case int64:
		return int(t)
	case json.Number:
		i, _ := t.Int64()
		return int(i)
	default:
		return 0
	}
}

func toInt64(v interface{}) int64 {
	switch t := v.(type) {
	case float64:
		return int64(t)
	case int:
		return int64(t)
	case int64:
		return t
	case json.Number:
		i, _ := t.Int64()
		return i
	default:
		return 0
	}
}
