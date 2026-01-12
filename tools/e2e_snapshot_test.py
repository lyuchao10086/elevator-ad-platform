"""
End-to-end snapshot test

Preconditions (you must run these manually before running this script):
- 启动 cloud 网关（Go）: 在 `elevator-ad-platform/cloud` 目录运行 `go run ./cmd` 或用 docker-compose 启动（网关监听 8080）。
- 启动 control-plane（FastAPI）: 在 `elevator-ad-platform/control-plane` 目录运行 `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`。

用途：
1. 作为一个设备（WebSocket 客户端）连接到网关 `/ws?device_id=...`。
2. 调用 control-plane 的 snapshot 路由：GET /api/v1/devices/{device_id}/snapshot。
3. 模拟设备在收到 SNAPSHOT 命令后，向 control-plane 的回调 `/api/v1/devices/snapshot/callback` 发送 base64 编码的图片数据。
4. 打印 control-plane 的 snapshot 返回结果，验证整体链路是否联通。

运行：
python tools/e2e_snapshot_test.py

"""

import threading
import time
import json
import base64
import requests
import websocket

# 配置（必要时修改）
DEVICE_ID = "ELEVATOR_SH_001"
GATEWAY_WS = "ws://127.0.0.1:8080/ws"
CONTROL_PLANE_SNAPSHOT_ENDPOINT = "http://127.0.0.1:8000/api/v1/devices/snapshot/callback"
CONTROL_PLANE_SNAPSHOT_ROUTE = f"http://127.0.0.1:8000/api/v1/devices/{DEVICE_ID}/snapshot"

# 小型示例“图片”内容（真实测试可替换为真实图片文件的 bytes）
SAMPLE_IMAGE_BYTES = b"FAKE_IMAGE_BYTES_FOR_TESTING"

ws_app = None


def device_on_message(ws, message):
    try:
        data = json.loads(message)
    except Exception:
        print("[device] Received non-json message:", message)
        return

    print(f"[device] 收到服务器消息: {data}")

    # 网关下发的命令消息在 handler.go 中是 {"type":"command","payload": <cmd>, "data": <...>} 
    if data.get("type") == "command":
        cmd = data.get("payload")
        print(f"[device] 收到命令: {cmd}")
        if cmd == "SNAPSHOT":
            # 模拟拍照并 POST 到 control-plane 的回调
            b64 = base64.b64encode(SAMPLE_IMAGE_BYTES).decode()
            body = {"device_id": DEVICE_ID, "snapshot_b64": b64}
            try:
                resp = requests.post(CONTROL_PLANE_SNAPSHOT_ENDPOINT, json=body, timeout=5)
                print(f"[device] 已发送 snapshot 回调，状态: {resp.status_code}, 响应: {resp.text}")
            except Exception as e:
                print(f"[device] 发送 snapshot 回调失败: {e}")


def device_on_error(ws, error):
    print("[device] WebSocket 错误:", error)


def device_on_close(ws, close_status_code, close_msg):
    print("[device] WebSocket 已关闭")


def device_on_open(ws):
    print(f"[device] 已连接到网关，device_id={DEVICE_ID}")


def run_device_client():
    global ws_app
    url = f"{GATEWAY_WS}?device_id={DEVICE_ID}&token=test_token"
    ws_app = websocket.WebSocketApp(
        url,
        on_message=device_on_message,
        on_error=device_on_error,
        on_close=device_on_close,
        on_open=device_on_open,
    )
    # run_forever 会阻塞，所以放在线程里
    ws_app.run_forever()


def main():
    # 启动模拟设备客户端
    t = threading.Thread(target=run_device_client, daemon=True)
    t.start()

    # 给点时间让 websocket 连接建立
    time.sleep(1.5)

    print("[test] 触发 control-plane snapshot 路由...")

    try:
        resp = requests.get(CONTROL_PLANE_SNAPSHOT_ROUTE, timeout=20)
    except Exception as e:
        print(f"[test] 请求 snapshot 路由失败: {e}")
        # 尝试清理 websocket
        try:
            if ws_app:
                ws_app.close()
        except Exception:
            pass
        return

    print(f"[test] snapshot 路由响应状态: {resp.status_code}")
    try:
        print("[test] 响应内容:", resp.json())
    except Exception:
        print("[test] 响应文本:", resp.text)

    # 结束 websocket
    try:
        if ws_app:
            ws_app.close()
    except Exception:
        pass


if __name__ == "__main__":
    main()
