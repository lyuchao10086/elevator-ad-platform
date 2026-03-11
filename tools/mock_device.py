import websocket
import json
import time
import threading
import random
import base64
import uuid

# 配置信息
GATEWAY_URL = "ws://127.0.0.1:8080/ws"
logs = [
    {
        "log_id": str(uuid.uuid4()),
        "device_id": "ELEV_002",
        "ad_id": "AD_公益_01",
        "ad_file_name": "resources/ads/public_welfare.jpg",

        "start_time": "2026-03-09 10:53:20",
        "end_time": "2026-03-09 10:53:30",
        "duration_ms": 10000,

        "status_code": 200,
        "status_msg": "Play Success",

        "created_at": int(time.time()),
        "device_ip": "192.168.31.69",
        "firmware_version": "1.0.0"
    },
    {
        "log_id": str(uuid.uuid4()),
        "device_id": "ELEV_003",
        "ad_id": "AD_LOGO_01",
        "ad_file_name": "resources/ads/ad_logo_01.jpg",

        "start_time": "2026-03-09 10:53:30",
        "end_time": "2026-03-09 10:53:40",
        "duration_ms": 10000,

        "status_code": 200,
        "status_msg": "Play Success",

        "created_at": int(time.time()),
        "device_ip": "192.168.31.69",
        "firmware_version": "1.0.0"
    }
]
def simulate_elevator(device_id, token): # 增加 token 参数
    """模拟单台电梯终端的逻辑"""
    
    # 动态拼接：使用传入的 ID 和 Token，不要硬编码
    ws_url = f"{GATEWAY_URL}?device_id={device_id}&token={token}"
    
    import os
    def on_message(ws, message):
        data = json.loads(message)
        
        # 1. 过滤心跳日志，保持终端干净
        if data.get("type") == "pong":
            return
            
        print(f"[{device_id}] 收到服务器指令: {data}")
        
        # --- 核心改动：兼容性判断 ---
        # 逻辑 A:  snapshot_request
        # 逻辑 B:  command + SNAPSHOT
        is_old_style = (data.get("type") == "snapshot_request")
        is_new_style = (data.get("type") == "command" and data.get("payload") == "SNAPSHOT")

        if is_old_style or is_new_style:
            # 统一提取 req_id
            req_id = data.get("req_id", "unknown") 
            print(f"[{device_id}] 📸 正在处理截图请求 (模式: {'旧' if is_old_style else '新'}), req_id={req_id}")
            
            # 读取本地图片逻辑（保持不变）
            try:
                with open(r"E:\repository\elevator-ad-platform\data\test_snapshot.jpg", "rb") as f:
                    img_bytes = f.read()
                img_b64 = base64.b64encode(img_bytes).decode("utf-8")
            except FileNotFoundError:
                img_b64 = "BASE64_MOCK_DATA" 
                print(f"[{device_id}] 警告: 未找到pg")

            # --- 关键点： test_snapshot.j构造回复消息 ---
            # 为了兼容你的 Go 后端 handler.go，必须使用 snapshot_response 且数据放在 payload 里
            snapshot_msg = {
                "type": "snapshot_response", # 匹配 handler.go 第 118 行的 case
                "device_id": device_id,
                "req_id": req_id,
                "ts": int(time.time()),
                "payload": {                 # 匹配 handler.go 第 150-155 行的解析结构
                    "format": "jpg",
                    "quality": 80,
                    "resolution": "1920x1080",
                    "data": img_b64          # 图片数据放在这里
                }
            }
            
            # 如果别人原来的逻辑还需要 snapshot_response 以外的类型，可以在这里加判断
            # 但根据你提供的 handler.go，Go 网关只认 snapshot_response
            
            ws.send(json.dumps(snapshot_msg))
            print(f"[{device_id}] ✅ 已上传截图回复 (req_id: {req_id})")

    def on_error(ws, error):
        print(f"[{device_id}] 错误: {error}")

    def on_close(ws, close_status_code, close_msg):
        print(f"[{device_id}] 连接已断开")

    def on_open(ws):
        """连接成功后的行为"""
        print(f"[{device_id}] 成功连接到 Go 网关")

        def send_loop():
            """循环发送心跳和日志"""
            while True:
                try:
                    # 1. 发送心跳包 (KeepAlive)
                    heartbeat = {
                        "type": "heartbeat",
                        "payload": "ping"
                    }
                    ws.send(json.dumps(heartbeat))
                    
                    # 2. 模拟上报播放日志 (RecordPlayLog)
                    if random.random() > 0.7:  # 模拟随机产生日志
                        log_data = {
                            "type": "log",
                            "payload": logs,
                        }
                        ws.send(json.dumps(log_data))
                        print(f"[{device_id}] 已上报播放日志")
                    
                    time.sleep(5)  # 每5秒交互一次
                except Exception as e:
                    print(f"[{device_id}] 发送数据失败: {e}")
                    break

        # 开启一个后台线程负责发送消息，不阻塞主监听循环
        threading.Thread(target=send_loop, daemon=True).start()

    # 启动 WebSocket 客户端
    ws = websocket.WebSocketApp(
        ws_url,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
        on_open=on_open
    )
    ws.run_forever()

if __name__ == "__main__":
    # --- 关键：在这里填入 Postman /register 接口给你的信息 ---
    # 你可以填多组，模拟多台真实注册过的设备
    my_real_devices = [
        {"id": "ELEV_001", "token": "sk_15b3acb1b0b84b01be6c7085e1271837"},
        # 如果有第二台，接着写：
        # {"id": "dev_xyz789", "token": "tok_999999"}
    ]
    
    threads = []
    for dev in my_real_devices:
        # 把 ID 和 Token 都传进去
        t = threading.Thread(target=simulate_elevator, args=(dev["id"], dev["token"]))
        t.start()
        threads.append(t)
        time.sleep(0.1)

    for t in threads:
        t.join()