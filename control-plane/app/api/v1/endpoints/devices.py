from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import base64

from app.services.device_service import send_remote_command, request_device_snapshot, receive_snapshot_callback

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

# 请求设备截图
@router.get("/{device_id}/snapshot")
async def get_snapshot(device_id: str):
    try:
        img = await request_device_snapshot(device_id)
        b64 = base64.b64encode(img).decode()
        return {"device_id": device_id, "snapshot_b64": b64}
    except TimeoutError as e:
        raise HTTPException(status_code=504, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 截图回调数据模型
class SnapshotCallback(BaseModel):
    device_id: str
    snapshot_b64: str

# 设备截图回调接口
@router.post("/snapshot/callback")
def snapshot_callback(body: SnapshotCallback):
    try:
        path = receive_snapshot_callback(body.device_id, body.snapshot_b64)
        return {"status": "ok", "path": path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
