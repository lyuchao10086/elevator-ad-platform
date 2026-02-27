import asyncio
import uuid
import os
from typing import Any, Optional
import requests
from app.core.config import settings

# 1. 维护每个设备当前正在等待快照的事件和数据
_waiters = {}
# 注意：在混合使用同步和异步时，我们直接用字典，依靠主线程的 call_soon_threadsafe 保证安全

def send_remote_command(device_id: str, command: str, data: Optional[str] = "", cmd_id: Optional[str] = None) -> dict:
    """通过 cloud 网关的 HTTP 接口下发命令

    支持可选的 `cmd_id` 字段，网关收到后会把该 id 透传到设备，设备回报时带回，网关会回调 control-plane 的 /commands/callback
    """
    url = settings.gateway_url.rstrip("/") + "/api/send"
    # `data` intentionally accepts both string and object payloads
    # (e.g. snapshot params or schedule JSON).
    payload = {"device_id": device_id, "command": command, "data": data}
    if cmd_id:
        payload["cmd_id"] = cmd_id
    resp = requests.post(url, json=payload, timeout=5)
    resp.raise_for_status()
    return {"status": "ok"}

# --- 之前被误删的函数，找回来了 ---
async def request_device_snapshot(device_id: str, timeout: Optional[int] = None) -> str:
    if timeout is None:
        timeout = settings.snapshot_wait_timeout
    
    # 创建异步等待事件
    event = asyncio.Event()
    _waiters[device_id] = {"event": event, "data": None}

    try:
        # 下发指令到 Go 网关
        send_remote_command(device_id, "SNAPSHOT", "")

        # 等待回调通知，直到超时
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(f"等待设备 {device_id} 截图超时 (15s)")

        entry = _waiters.get(device_id)
        if not entry or not entry["data"]:
            raise RuntimeError("截图回调数据为空")
            
        return entry["data"] # 返回图片的 OSS URL
    finally:
        # 无论成功还是超时，都要清理掉，防止内存泄露
        _waiters.pop(device_id, None)

# --- 修复后的回调函数：删掉了旧的重复定义，使用 threadsafe 写法 ---
async def receive_snapshot_callback(device_id: str, snapshot_url: str) -> str:
    """
    由 Go 网关触发的同步回调接口调用此函数
    """
    print(f"✅ [Service] 尝试唤醒请求: {device_id}")
    
    entry = _waiters.get(device_id)
    if entry:
        entry["data"] = snapshot_url
        event = entry["event"]
        
        # 关键：确保在创建 event 的那个主线程循环里 set()
        # event._loop 是 asyncio.Event 内部维护的引用
        loop = event._loop
        loop.call_soon_threadsafe(event.set)
        
        print(f"✅ [Service] 成功通知主循环：URL 已填入")
    else:
        print(f"⚠️ [Service] 收到回调但没找到对应的等待请求: {device_id}")

    return snapshot_url
