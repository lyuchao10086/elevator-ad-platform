import requests
import json
from flask import Flask, request, jsonify
import requests
import threading
import time
#向GO网关发送指令
def push_command_to_elevator(device_id, command_type, extra_data):
    # 网关的北向接口地址 (对应你 main.go 里的 /api/send)
    url = "http://127.0.0.1:8080/api/send"
    
    # 构建发送给 Go 网关的 JSON 数据
    # 结构必须对应你 handler.go 中 HandleCommand 函数里的 req 结构体
    payload = {
        "device_id": device_id,
        "command": command_type,
        "data": extra_data
    }

    print(f"正在向网关发送指令: {command_type} -> 设备: {device_id}")

    try:
        # 发送 POST 请求
        response = requests.post(url, json=payload)
        
        if response.status_code == 200:
            print("✅ 指令成功送达网关")
        elif response.status_code == 404:
            print("❌ 发送失败：该设备目前不在线（网关内存中找不到连接）")
        else:
            print(f"⚠️ 网关返回异常: {response.status_code} - {response.text}")
            
    except Exception as e:
        print(f"🚀 无法连接到网关: {e}")

# ------------------------------
# 2️⃣ 接收设备上线/掉线通知
app = Flask(__name__)

# 存储设备状态
device_status = {}

@app.route("/api/device/status", methods=["POST"])
def device_status_update():
    data = request.json
    device_id = data.get("device_id")
    status = data.get("status")  # online/offline
    event_time = data.get("event_time", int(time.time()))

    # 更新本地状态表
    device_status[device_id] = {
        "status": status,
        "last_update": event_time
    }

    print(f"[Python] 设备状态变更: {device_id} -> {status} at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(event_time))}")
    return jsonify({"code": 0, "message": "ok"})
if __name__ == "__main__":
    # 测试案例 1：让 001 号电梯重启
    #push_command_to_elevator("ELEVATOR_SH_001", "REBOOT", "force=true")
    
    # 启动 Flask 后端 监听设备在线/掉线
    print("[Python] 后端启动，监听设备状态变化...")
    app.run(host="0.0.0.0", port=5000)

    # 测试案例 2：让 002 号电梯更新视频列表
    # push_command_to_elevator("ELEVATOR_SH_002", "UPDATE_PLAYLIST", "url=http://cdn.com/v2.json")