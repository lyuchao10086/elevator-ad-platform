import requests
import json
from flask import Flask, request, jsonify
import requests
import threading
import time
import redis
# 连接 Redis
r = redis.Redis(host='127.0.0.1', port=6379, db=0, decode_responses=True)

#向GO网关发送指令
def push_command_to_elevator(device_id, command_type, extra_data):
    # 网关的snapshot请求接口地址 (对应你 main.go 里的 /api/send)
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
# 新增一个「远程截图请求函数」
def request_remote_snapshot(device_id):
    url = f"http://127.0.0.1:8080/api/v1/devices/remote/{device_id}/snapshot"

    print(f"[Python] 请求设备截图: {device_id}")

    try:
        resp = requests.get(url, timeout=5)

        if resp.status_code == 200:
            data = resp.json()
            req_id = data.get("req_id")
            print(f"✅ 截图请求已受理 req_id={req_id}")
            return req_id
        elif resp.status_code == 404:
            print("❌ 设备不在线")
        else:
            print(f"⚠️ 网关异常: {resp.status_code} {resp.text}")
    except Exception as e:
        print(f"🚀 请求失败: {e}")

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
#回调接口（GO回调截图完成）
@app.route("/api/v1/devices/remote/snapshot/callback", methods=["POST"])
def snapshot_callback():
    data = request.get_json()

    device_id = data.get("device_id")
    req_id = data.get("req_id")
    snapshot_url = data.get("snapshot_url")

    print(
        f"[Python] 收到截图回调 "
        f"device={device_id}, req={req_id}, url={snapshot_url}"
    )

    return jsonify({"code": 0, "message": "ok"}), 200

# 监听设备在线/掉线线程
def run_flask():
    print("[Python] 后端启动，监听设备状态变化...")
    app.run(port=8000)

#向设备发起截图请求进程
def business_logic():
    time.sleep(5)  # 等待设备上线
    print("[Python] 向设备发送截图请求")
    # push_command_to_elevator(
    #     device_id="ELEVATOR_53D246",
    #     command_type="CAPTURE_SCREEN",
    #     extra_data={
    #         "req_id": "req-001"
    #     }
    # )
    request_remote_snapshot("ELEVATOR_53D246")
#读取日志
def consume_stream():
    stream_name = "play_log_stream"
    group_name = "cloud_group"
    consumer_name = "consumer_1"

    while True:
        # 从消费组读取消息
        resp = r.xreadgroup(
            groupname=group_name,
            consumername=consumer_name,
            streams={stream_name: '>'},  # '>' 表示只读取尚未被消费的消息
            count=10,
            block=5000
        )

        if not resp:
            continue

        for stream, messages in resp:
            for msg_id, msg_data in messages:
                # 解析 JSON
                for k, v in msg_data.items():
                    try:
                        msg_data[k] = json.loads(v)
                    except:
                        pass
                print(f"消费到日志 {msg_id}: {msg_data}")

                # 处理完成后确认消息
                r.xack(stream_name, group_name, msg_id)
if __name__ == "__main__":
    # 测试案例 1：让 001 号电梯重启
    #push_command_to_elevator("ELEVATOR_SH_001", "REBOOT", "force=true")
    
    # 启动 Flask 后端 监听设备在线/掉线
    # print("[Python] 后端启动，监听设备状态变化...")
    # app.run(host="0.0.0.0", port=5000)

    # 测试案例 2：让 002 号电梯更新视频列表
    # push_command_to_elevator("ELEVATOR_SH_002", "UPDATE_PLAYLIST", "url=http://cdn.com/v2.json")
    
    # 测试案例 3： 让 001 号电梯设备截图
    # flask_thread = threading.Thread(target=run_flask, daemon=True)
    # flask_thread.start()

    # business_thread = threading.Thread(target=business_logic, daemon=True)
    # business_thread.start()

    # 测试案例 4 ：读取日志消息
    consumer_thread = threading.Thread(target=consume_stream, daemon=True)
    consumer_thread.start()
    # 防止主线程退出
    while True:
        time.sleep(1)
