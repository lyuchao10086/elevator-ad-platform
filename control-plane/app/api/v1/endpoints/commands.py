from fastapi import APIRouter, Body, HTTPException
from typing import Dict, Any
import time
import uuid

# 导入你之前调通的截图服务
from app.services.device_snapshot_service import request_device_snapshot

router = APIRouter()

# 模拟内存数据库，用来存一下发过的指令记录（重启后会清空）
# 这样你的前端下方表格就能看到记录了
mock_command_db = []

@router.get("")
async def list_commands(limit: int = 20):
    """
    获取指令历史列表
    前端 Commands.vue 会自动调用这个接口
    """
    # 按时间倒序返回
    sorted_cmds = sorted(mock_command_db, key=lambda x: x.get("send_ts", 0), reverse=True)
    return {
        "items": sorted_cmds[:limit],
        "total": len(mock_command_db)
    }

@router.post("")
async def send_command(payload: Dict[str, Any] = Body(...)):
    """
    下发指令接口
    前端点击“发送指令”时调用
    """
    action = payload.get("action")
    device_id = payload.get("target_device_id")
    cmd_id = payload.get("cmd_id") or str(uuid.uuid4())
    
    # 记录这条指令到内存库
    record = {
        "cmd_id": cmd_id,
        "device_id": device_id,
        "action": action,
        "status": "pending",
        "send_ts": int(time.time()),
        "result": None
    }
    
    print(f"📡 [Commands] 收到指令: {action} -> {device_id}")

    try:
        # --- 核心联动逻辑 ---
        if action == "capture":
            # 1. 只有动作是截屏时，才调用截图服务
            print(f"📸 触发截图流程: {device_id}")
            
            # 这里会挂起等待，直到 Go 回调或超时
            # 因为 request_device_snapshot 内部有 15秒超时机制，所以这里是安全的
            img_url = await request_device_snapshot(device_id)
            
            # 2. 拿到结果，更新记录
            record["status"] = "success"
            record["result"] = img_url # 这个 URL 会被前端拿到并展示
            mock_command_db.append(record)
            
            return {
                "status": "success",
                "cmd_id": cmd_id,
                "data": {"url": img_url} # 适配前端可能的读取方式
            }

        else:
            # 对于重启、设置音量等其他指令，暂时只做模拟返回
            # 实际项目中，你需要调用 Go 网关下发指令
            record["status"] = "sent"
            mock_command_db.append(record)
            
            return {
                "status": "success",
                "cmd_id": cmd_id,
                "msg": f"指令 {action} 已下发至网关"
            }

    except TimeoutError:
        record["status"] = "timeout"
        mock_command_db.append(record)
        raise HTTPException(status_code=504, detail="设备响应超时")
        
    except Exception as e:
        print(f"❌ 指令执行出错: {e}")
        record["status"] = "failed"
        mock_command_db.append(record)
        raise HTTPException(status_code=500, detail=str(e))