import asyncio
import base64
import os
import uuid
from typing import Optional

import requests

from app.core.config import settings


# 维护每个设备当前正在等待快照的事件和数据
_waiters = {}
_waiters_lock = asyncio.Lock()


def send_remote_command(device_id: str, command: str, data: Optional[str] = "") -> dict:
    """通过 cloud 网关的 HTTP 接口下发命令。

    返回网关的 HTTP 响应 JSON（若有）。
    """
    url = settings.gateway_url.rstrip("/") + "/api/send"
    payload = {"device_id": device_id, "command": command, "data": data}
    resp = requests.post(url, json=payload, timeout=5)
    resp.raise_for_status()
    if resp.content:
        try:
            return resp.json()
        except Exception:
            return {"status": "ok"}
    return {"status": "ok"}


async def request_device_snapshot(device_id: str, timeout: Optional[int] = None) -> bytes:
    """请求设备截图并等待 control-plane 回调上报截图（base64）。

    机制：向 gateway 下发 SNAPSHOT 命令；同时在内存注册一个等待器，等待 callback 写入。
    若超时则抛出 TimeoutError。
    """
    if timeout is None:
        timeout = settings.snapshot_wait_timeout
    # 注册等待器
    async with _waiters_lock:
        if device_id in _waiters:
            raise RuntimeError("已有未完成的 snapshot 请求在进行中")
        #  创建 asyncio.Event 并保存到 _waiters，随后通过 await 等待该事件被回调触发。
        event = asyncio.Event()
        _waiters[device_id] = {"event": event, "data": None}

    try:
        # 触发网关下发命令（同步 HTTP 调用）
        send_remote_command(device_id, "SNAPSHOT", "")

        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            raise TimeoutError("等待设备截图超时")

        # 获取数据
        async with _waiters_lock:
            entry = _waiters.get(device_id)
            if not entry or not entry["data"]:
                raise RuntimeError("截图未到达")
            return entry["data"]
    finally:
        async with _waiters_lock:
            _waiters.pop(device_id, None)


def _save_snapshot_bytes(device_id: str, img_bytes: bytes) -> str:
    d = settings.snapshot_storage_dir
    os.makedirs(d, exist_ok=True)
    fname = f"{device_id}_{uuid.uuid4().hex}.jpg"
    path = os.path.join(d, fname)
    with open(path, "wb") as f:
        f.write(img_bytes)
    return path


def receive_snapshot_callback(device_id: str, snapshot_b64: str) -> str:
    """被回调时调用：保存文件，并通知等待器（若存在）。

    返回保存的本地路径。
    """
    img = base64.b64decode(snapshot_b64)
    path = _save_snapshot_bytes(device_id, img)

    # 通知等待器（若有）
    loop = asyncio.get_event_loop()

    async def _notify():
        async with _waiters_lock:
            entry = _waiters.get(device_id)
            if entry:
                entry["data"] = img
                entry["event"].set()

    try:
        # 在事件循环中通知
        if loop.is_running():
            asyncio.ensure_future(_notify())
        else:
            loop.run_until_complete(_notify())
    except Exception:
        # 忽略通知异常，但文件已保存
        pass

    return path
