import requests
import json

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

if __name__ == "__main__":
    # 测试案例 1：让 001 号电梯重启
    push_command_to_elevator("ELEVATOR_SH_001", "REBOOT", "force=true")
    
    # 测试案例 2：让 002 号电梯更新视频列表
    # push_command_to_elevator("ELEVATOR_SH_002", "UPDATE_PLAYLIST", "url=http://cdn.com/v2.json")