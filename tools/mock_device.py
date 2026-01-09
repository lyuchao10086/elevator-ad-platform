import websocket
import json
import time
import threading
import random

# 配置信息
GATEWAY_URL = "ws://127.0.0.1:8080/ws"

def simulate_elevator(device_id):
    """模拟单台电梯终端的逻辑"""
    
    # 根据文档 A.连接管理：建立连接并带上 device_id 参数
    ws_url = f"{GATEWAY_URL}?device_id={device_id}&token=test_token_123"
    
    def on_message(ws, message):
        """处理来自 Go 网关的下行指令 (PushCommand)"""
        data = json.loads(message)
        print(f"[{device_id}] 收到服务器指令: {data}")
        
        # 如果收到 pong，说明心跳成功
        if data.get("type") == "pong":
            pass # 可以在这里更新本地连接活跃时间

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
    # 定义要模拟的设备列表
    # 在实际测试中，你可以把 range 改成 1000 来测试网关性能
    test_devices = [f"ELEVATOR_SH_00{i}" for i in range(1, 4)]
    
    threads = []
    print(f"正在启动 {len(test_devices)} 台模拟设备...")

    for dev_id in test_devices:
        t = threading.Thread(target=simulate_elevator, args=(dev_id,))
        t.start()
        threads.append(t)
        time.sleep(0.1)  # 避免瞬间并发过高

    for t in threads:
        t.join()