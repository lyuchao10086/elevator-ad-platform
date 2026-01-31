import websocket
import json
import time
import threading
import random
import base64

# 配置信息
GATEWAY_URL = "ws://127.0.0.1:8080/ws"

def simulate_elevator(device_id, token): # 增加 token 参数
    """模拟单台电梯终端的逻辑"""
    
    # 动态拼接：使用传入的 ID 和 Token，不要硬编码
    ws_url = f"{GATEWAY_URL}?device_id={device_id}&token={token}"
    
    def on_message(ws, message):
        data = json.loads(message)
        print(f"[{device_id}] 收到服务器指令: {data}")
        
        if data.get("type") == "pong":
            pass
            
        # 注意：这里判断指令类型要跟 Python 后端发的一致
        # 如果你后端发的是 SNAPSHOT，这里就改 SNAPSHOT
    
        
        if data.get("type") == "snapshot_request" :
            # 获取请求 ID
            req_id = data.get("req_id", "unknown") 
            payload = data.get("payload", {})
            print(f"[{device_id}] 开始处理截图请求 req_id={req_id}, 参数={payload}")
            # 读取本地图片(用一张固定图片做测试)
            try:
                with open("test_snapshot.jpg", "rb") as f:
                    img_bytes = f.read()
                img_b64 = base64.b64encode(img_bytes).decode("utf-8")
            except FileNotFoundError:
                img_b64 = "BASE64_MOCK_DATA" # 没图片就发假数据测试
                print(f"[{device_id}] 警告: 未找到 test_snapshot.jpg")

            snapshot_msg = {
                "type": "snapshot_response",
                "device_id": device_id, # 必须是当前连接的 ID
                "req_id": req_id,       # 必须把 req_id 原样传回，否则 Python 认不出是谁的回复
                "ts": int(time.time()),
                "payload": {
                    "format": "jpeg",
                    "data": img_b64
                }
            }

            ws.send(json.dumps(snapshot_msg))
            print(f"[{device_id}] 已上传截图回复")

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
                            "payload": f"Device {device_id} is playing Ad_Video_{random.randint(100, 999)}.mp4"
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
        {"id": "ELEVATOR_53D246", "token": "sk_15b3acb1b0b84b01be6c7085e1271837"},
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