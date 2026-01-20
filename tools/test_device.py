import websocket
import json
import time
import threading

#模拟一台 ID 为 ELEVATOR_001 的电梯。
def on_message(ws, message):
    print(f"确认收到网关回复: {message}")

def on_error(ws, error):
    print(f"发生错误: {error}")

def on_close(ws, close_status_code, close_msg):
    print("### 连接已断开 ###")

def on_open(ws):
    print("### 已连接到网关 ###")
    
    # 模拟发送心跳和日志的循环
    def run(*args):
        # 1. 先发送一个登录/鉴权消息 (假设你的协议需要)
        # 2. 定期发送心跳
        for i in range(10):
            time.sleep(2)
            heartbeat = {
                "type": "heartbeat",
                "device_id": "ELEVATOR_001",
                "payload": {}
            }
            ws.send(json.dumps(heartbeat))
            print("已发送心跳...")

            # 模拟发送一条日志
            log_msg = {
                "type": "log",
                "device_id": "ELEVATOR_001",
                "payload": f"正在播放广告视频_{i}.mp4"
            }
            ws.send(json.dumps(log_msg))
            print("已发送日志...")

        time.sleep(5)
        ws.close()
    
    threading.Thread(target=run).start()

if __name__ == "__main__":
    # test_device.py
    ws_url = "ws://127.0.0.1:8080/ws?device_id=ELEVATOR_001&token=secret123"
    
    ws = websocket.WebSocketApp(ws_url,
                              on_open=on_open,
                              on_message=on_message,
                              on_error=on_error,
                              on_close=on_close)
    ws.run_forever()