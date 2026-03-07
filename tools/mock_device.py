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

        # 逻辑 C: 通用 command（重启、设置音量、插播等）
        is_command = (data.get("type") == "command")

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
        elif is_command:
            # 处理通用 command，模拟设备执行并回执 command_response
            cmd = (data.get("payload") or "").upper()
            cmd_id = data.get("cmd_id") or ""
            cmd_data = data.get("data") or {}
            print(f"[{device_id}] mock设备收到通用命令: {cmd} (cmd_id={cmd_id}) data={cmd_data}")

            # 模拟执行延迟
            time.sleep(1)

            # 根据命令构造结果
            result = "ok"
            if cmd == 'REBOOT':
                result = 'reboot_ok'
            elif cmd == 'SET_VOLUME' or cmd == 'SET_VOLUME'.upper():
                # 支持两种key：volume 或 params.volume
                vol = None
                mute = None
                if isinstance(cmd_data, dict):
                    vol = cmd_data.get('volume')
                    mute = cmd_data.get('mute')
                result = f"set_volume:{vol}|mute:{mute}"
            elif cmd == 'INSERT_PLAY' or cmd == 'INSERT_PLAY'.upper() or cmd == 'INSERT_PLAY'.lower():
                mid = None
                priority = None
                if isinstance(cmd_data, dict):
                    mid = cmd_data.get('material_id') or cmd_data.get('material')
                    priority = cmd_data.get('priority')
                result = f"insert_play:{mid}|priority:{priority}"
            else:
                result = f"{cmd}_ok"

            resp = {
                "type": "command_response",
                "device_id": device_id,
                "req_id": data.get("req_id", ""),
                "ts": int(time.time()),
                "payload": {
                    "cmd_id": cmd_id,
                    "status": "success",
                    "result": result
                }
            }
            ws.send(json.dumps(resp))
            print(f"[{device_id}] ✅ 已发送 command_response (cmd_id={cmd_id}) result={result}")

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
                            "payload": {
                                "log_id": "log_10002",
                                "ad_id": "ad_999",
                                "playback_info": {
                                    "duration_ms": 15000,
                                    "status_code": 0
                                },
                                "meta": {}
                            }
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
    # 尝试从 Redis 中读取已注册设备（key set: registered_devices, token 保存在 auth:<device_id>）
    import os
    my_real_devices = []
    try:
        use_redis = os.environ.get('USE_REDIS_DEVICES', '1')
        if use_redis in ('1', 'true', 'True', 'TRUE'):
            import redis
            rdb = redis.Redis(host=os.environ.get('REDIS_HOST','localhost'), port=int(os.environ.get('REDIS_PORT','6379')), db=int(os.environ.get('REDIS_DB','0')), decode_responses=True)
            ids = []
            try:
                ids = list(rdb.smembers('registered_devices') or [])
            except Exception:
                ids = []
            for did in ids:
                try:
                    token = rdb.get(f'auth:{did}')
                    if token:
                        my_real_devices.append({ 'id': did, 'token': token })
                except Exception:
                    continue
    except Exception:
        my_real_devices = []

    # 如果 Redis 中没有可用设备，退回到硬编码示例
    if not my_real_devices:
        my_real_devices = [
            {"id": "ELEV_001", "token": "sk_15b3acb1b0b84b01be6c7085e1271837"},
            {"id": "ELEV_010", "token": "sk_15b3acb1b0b84b01be6c7085e1271865"},
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