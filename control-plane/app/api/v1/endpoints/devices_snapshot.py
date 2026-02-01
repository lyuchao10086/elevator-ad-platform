from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import base64

from app.services.device_snapshot_service import send_remote_command, request_device_snapshot, receive_snapshot_callback

router = APIRouter()


class CommandRequest(BaseModel):
    device_id: str
    command: str
    data: str = ""

# 发送命令到设备
@router.post("/command")
def post_command(req: CommandRequest):
    try:
        res = send_remote_command(req.device_id, req.command, req.data)
        return {"status": "ok", "result": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 修改 1: 获取截图接口，直接返回 URL
@router.get("/{device_id}/snapshot")
async def get_snapshot(device_id: str):
    try:
        # 这里返回的不再是 bytes，而是 url 字符串
        snapshot_url = await request_device_snapshot(device_id)
        return {"device_id": device_id, "snapshot_url": snapshot_url}
    except TimeoutError as e:
        raise HTTPException(status_code=504, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
# 截图回调数据模型
# 修改 2: 回调数据模型，适配 Go 发来的 JSON
class SnapshotCallback(BaseModel):
    device_id: str
    req_id: Optional[str] = None         # Go 发来的请求 ID
    snapshot_url: str   # Go 发来的 OSS 地址

# 设备截图回调接口
@router.post("/snapshot/callback")
async def snapshot_callback(body: SnapshotCallback):
    try:
        # 传递 url 而不是 base64
        # path = receive_snapshot_callback(body.device_id, body.snapshot_url)
        #改为异步调用
        path = await receive_snapshot_callback(body.device_id, body.snapshot_url)
        return {"status": "ok", "url": path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))