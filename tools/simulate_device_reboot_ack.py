#!/usr/bin/env python3
"""
模拟设备：连接到 cloud 网关的 WebSocket，并在收到 REBOOT 指令时发送 command_response 回执。

用法：
    python tools/simulate_device_reboot_ack.py ELEVATOR_53D246 my_token

保持简单，依赖 websocket-client（pip install websocket-client）。
"""
import sys
import time
import json
import threading
from websocket import WebSocketApp

GATEWAY_URL = "ws://127.0.0.1:8080/ws"


def run_device(device_id, token):
    ws_url = f"{GATEWAY_URL}?device_id={device_id}&token={token}"

    def on_message(ws, message):
        data = json.loads(message)
        print(f"[{device_id}] 收到: {data}")

        if data.get("type") == "command":
            payload = data.get("payload")
            cmd_id = data.get("cmd_id", "")
            # 支持 payload 可能为字符串或对象
            if isinstance(payload, str) and payload.upper() == "REBOOT":
                print(f"[{device_id}] 收到 REBOOT，准备回执 cmd_id={cmd_id}")
                # 先回执 success
                resp = {
                    "type": "command_response",
                    "device_id": device_id,
                    "req_id": "",
                    "ts": int(time.time()),
                    "payload": {
                        "cmd_id": cmd_id,
                        "status": "success",
                        "result": "rebooting"
                    }
                }
                ws.send(json.dumps(resp))
                print(f"[{device_id}] 已发送 command_response (success)")
                # 模拟设备重启：短暂断开连接
                def do_reboot():
                    time.sleep(1)
                    try:
                        ws.close()
                        print(f"[{device_id}] 模拟断开（重启）")
                    except Exception:
                        pass

                threading.Thread(target=do_reboot, daemon=True).start()

    def on_open(ws):
        print(f"[{device_id}] 已连接到网关 {ws_url}")

        def heartbeat():
            while True:
                try:
                    hb = {"type": "heartbeat", "payload": "ping"}
                    ws.send(json.dumps(hb))
                    time.sleep(5)
                except Exception:
                    break

        threading.Thread(target=heartbeat, daemon=True).start()

    def on_close(ws, code, reason):
        print(f"[{device_id}] 连接关闭: {code} {reason}")

    def on_error(ws, err):
        print(f"[{device_id}] 错误: {err}")

    ws = WebSocketApp(ws_url, on_open=on_open, on_message=on_message, on_close=on_close, on_error=on_error)
    ws.run_forever()


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("用法: python tools/simulate_device_reboot_ack.py <device_id> <token>")
        sys.exit(1)

    device_id = sys.argv[1]
    token = sys.argv[2]
    run_device(device_id, token)
