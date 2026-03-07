from fastapi import APIRouter, Body, HTTPException
from typing import Dict, Any
import time
import uuid

# 导入你之前调通的截图服务
from app.services.device_snapshot_service import request_device_snapshot, send_remote_command
from app.services import db_service

router = APIRouter()

# 模拟内存数据库，用来存一下发过的指令记录（重启后会清空）
# 这样你的前端下方表格就能看到记录了
mock_command_db = []

@router.get("")
async def list_commands(limit: int = 20, offset: int = 0, device_id: str = None, action: str = None, from_ts: int = None, to_ts: int = None, q: str = None):
    """
    获取指令历史列表，优先从数据库读取 `command_logs`，若 DB 不可用回退到内存 mock。
    支持分页与按设备过滤。
    """
    try:
        rows = db_service.list_commands(limit=limit, offset=offset, q=q, device_id=device_id, action=action, from_ts=from_ts, to_ts=to_ts)
        # debug info: print how many rows returned and sample
        try:
            print(f"[commands] read from DB, count={len(rows)}")
            if len(rows):
                import json
                sample = dict(rows[0])
                print("[commands] sample:", json.dumps(sample, default=str)[:1000])
        except Exception:
            pass
        # compute total count matching filters for correct pagination
        try:
            total = db_service.count_commands(q=q, device_id=device_id, action=action, from_ts=from_ts, to_ts=to_ts)
        except Exception:
            total = len(rows)
        return {"items": rows, "total": total}
    except Exception as e:
        # 回退到内存 mock，保持原有行为
        print(f"[commands] db read failed, fallback to mock: {e}")
        sorted_cmds = sorted(mock_command_db, key=lambda x: x.get("send_ts", 0), reverse=True)
        filtered = sorted_cmds
        if device_id:
            filtered = [c for c in filtered if c.get('device_id') == device_id]
        if q:
            ql = q.lower()
            filtered = [c for c in filtered if ql in (str(c.get('cmd_id') or '')).lower() or ql in (str(c.get('device_id') or '')).lower() or ql in (str(c.get('action') or '')).lower()]
        return {"items": filtered[offset:offset+limit], "total": len(filtered)}

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
            # 尝试持久化到 DB，若失败则回退到内存 mock
            try:
                db_service.insert_command({
                    "cmd_id": record.get("cmd_id"),
                    "device_id": record.get("device_id"),
                    "action": record.get("action"),
                    "params": payload.get('params', {}),
                    "status": record.get("status"),
                    "result": record.get("result"),
                    "send_ts": record.get("send_ts")
                })
            except Exception as e:
                print(f"[commands] insert_command failed, fallback to mock: {e}")
                mock_command_db.append(record)
            
            return {
                "status": "success",
                "cmd_id": cmd_id,
                "data": {"url": img_url} # 适配前端可能的读取方式
            }

        else:
            # 对于重启、设置音量等其他指令，尝试调用 Go 网关下发真实指令
            try:
                # 从前端 payload 里取 params（可能是 dict 或其他可序列化对象）并透传给网关
                data = payload.get('params', {}) if isinstance(payload, dict) else {}
                if action == "reboot":
                    # 将前端的 reboot 动作映射为网关/设备端的 REBOOT 命令
                    send_remote_command(device_id, "REBOOT", data, cmd_id)
                    print(f"[commands] 重启data:{data}")
                    record["status"] = "sent"
                    record["result"] = "reboot_sent"
                else:
                    # 其他动作将 params 一并传输，设备端可从 data 字段读取
                    send_remote_command(device_id, action.upper(), data, cmd_id)
                    record["status"] = "sent"
                    record["result"] = f"{action}_sent"

                # 先持久化到 DB（若可用），再回退到内存
                try:
                    db_service.insert_command({
                        "cmd_id": record.get("cmd_id"),
                        "device_id": record.get("device_id"),
                        "action": record.get("action"),
                        "params": payload.get('params', {}),
                        "status": record.get("status"),
                        "result": record.get("result"),
                        "send_ts": record.get("send_ts")
                    })
                except Exception as e:
                    print(f"[commands] insert_command failed, fallback to mock: {e}")
                    mock_command_db.append(record)

                return {
                    "status": "success",
                    "cmd_id": cmd_id,
                    "msg": f"指令 {action} 已下发至网关"
                }
            except Exception as e:
                record["status"] = "failed"
                record["result"] = str(e)
                try:
                    db_service.insert_command({
                        "cmd_id": record.get("cmd_id"),
                        "device_id": record.get("device_id"),
                        "action": record.get("action"),
                        "params": payload.get('params', {}),
                        "status": record.get("status"),
                        "result": record.get("result"),
                        "send_ts": record.get("send_ts")
                    })
                except Exception:
                    mock_command_db.append(record)
                raise HTTPException(status_code=500, detail=f"下发指令失败: {e}")
    except TimeoutError:
        record["status"] = "timeout"
        mock_command_db.append(record)
        raise HTTPException(status_code=504, detail="设备响应超时")

    except Exception as e:
        print(f"❌ 指令执行出错: {e}")
        record["status"] = "failed"
        mock_command_db.append(record)
        raise HTTPException(status_code=500, detail=str(e))
@router.post("/callback")
async def command_callback(body: Dict[str, Any] = Body(...)):
    """网关回调 control-plane，告知某条指令的执行结果

    期望 body 中包含: `cmd_id`, `device_id`, `status` (success/failed), `result` (optional 描述)
    """
    cmd_id = body.get("cmd_id")
    device_id = body.get("device_id")
    status = body.get("status")
    result = body.get("result")

    if not cmd_id and not device_id:
        raise HTTPException(status_code=400, detail="missing cmd_id or device_id")

    # 找到对应记录（优先按 cmd_id 匹配）并更新状态
    updated = False
    # Try update DB first
    try:
        if cmd_id:
            rows = db_service.update_command_status(cmd_id=cmd_id, status=status, result=result)
            if rows and rows > 0:
                print(f"[commands.callback] updated DB by cmd_id={cmd_id}, rows={rows}")
                updated = True
    except Exception as e:
        print(f"[commands.callback] db update by cmd_id failed: {e}")

    # If DB not updated, try update in-memory mock by cmd_id
    if not updated:
        for rec in mock_command_db:
            if cmd_id and rec.get("cmd_id") == cmd_id:
                rec["status"] = status or rec.get("status")
                rec["result"] = result or rec.get("result")
                updated = True
                break

    # 如果没有 cmd_id，尝试按 device_id 更新最近一条 pending/sent 指令
    if not updated and device_id:
        # Try DB update by device_id
        try:
            rows = db_service.update_command_status(device_id=device_id, status=status, result=result)
            if rows and rows > 0:
                print(f"[commands.callback] updated DB by device_id={device_id}, rows={rows}")
                updated = True
        except Exception as e:
            print(f"[commands.callback] db update by device_id failed: {e}")

        # If DB not updated, fall back to in-memory update
        if not updated:
            for rec in sorted(mock_command_db, key=lambda x: x.get("send_ts", 0), reverse=True):
                if rec.get("device_id") == device_id and rec.get("status") in ("sent", "pending"):
                    rec["status"] = status or rec.get("status")
                    rec["result"] = result or rec.get("result")
                    updated = True
                    break

    if not updated:
        # 若没找到记录，仍返回成功以避免网关重试，但记录日志
        print(f"⚠️ [Commands Callback] 未找到对应记录 cmd_id={cmd_id} device_id={device_id}")

    return {"status": "ok"}
    