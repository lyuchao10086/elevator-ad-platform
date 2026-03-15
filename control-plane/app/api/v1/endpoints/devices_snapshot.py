from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.device_snapshot_service import (
    send_remote_command,
    request_device_snapshot,
    receive_snapshot_callback,
)

router = APIRouter()


class CommandRequest(BaseModel):
    device_id: str
    command: str
    data: str = ""


# 通用远程命令入口，主要用于调试和联调。
# 实际命令分发仍由 service 层统一转发到 Go 网关。
@router.post("/command")
def post_command(req: CommandRequest):
    try:
        res = send_remote_command(req.device_id, req.command, req.data)
        return {"status": "ok", "result": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 截图接口直接返回 snapshot_url，而不是返回图片二进制。
# 这样 control-plane 只负责命令编排，不承担图片内容中转。
@router.get("/{device_id}/snapshot")
async def get_snapshot(device_id: str):
    try:
        snapshot_url = await request_device_snapshot(device_id)
        return {"device_id": device_id, "snapshot_url": snapshot_url}
    except TimeoutError as e:
        raise HTTPException(status_code=504, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Go 网关回调截图结果时使用的请求模型。
# req_id 用于把这次回调和之前的命令日志关联起来。
class SnapshotCallback(BaseModel):
    device_id: str
    req_id: Optional[str] = None
    snapshot_url: str


# 网关拿到设备截图结果后，会回调这个接口。
# 这里不处理图片内容，只负责唤醒等待中的请求并更新命令状态。
@router.post("/snapshot/callback")
async def snapshot_callback(body: SnapshotCallback):
    try:
        path = await receive_snapshot_callback(body.device_id, body.snapshot_url, body.req_id)
        return {"status": "ok", "url": path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
