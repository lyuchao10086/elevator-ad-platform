import asyncio
import json
from fastapi import APIRouter, Body, HTTPException
from typing import Dict, Any, List
import time
import uuid

# 导入你之前调通的截图服务
from app.services.device_snapshot_service import request_device_snapshot, send_remote_command
from app.services import db_service

router = APIRouter()

# 模拟内存数据库，用来存一下发过的指令记录（重启后会清空）
# 这样你的前端下方表格就能看到记录了
mock_command_db = []


def _normalize_action(action: Any) -> str:
    if not isinstance(action, str):
        raise HTTPException(status_code=400, detail="action is required")
    action = action.strip().lower()
    if not action:
        raise HTTPException(status_code=400, detail="action is required")
    return action


def _extract_target_devices(payload: Dict[str, Any]) -> List[str]:
    devices: List[str] = []
    single = payload.get("target_device_id")
    multiple = payload.get("target_device_ids")

    if isinstance(single, str) and single.strip():
        devices.append(single.strip())

    if isinstance(multiple, list):
        for item in multiple:
            if isinstance(item, str) and item.strip():
                devices.append(item.strip())

    unique = []
    seen = set()
    for d in devices:
        if d not in seen:
            unique.append(d)
            seen.add(d)

    if not unique:
        raise HTTPException(status_code=400, detail="target_device_id or target_device_ids is required")
    return unique


def _normalize_insert_play_params(payload: Dict[str, Any]) -> Dict[str, Any]:
    raw = payload.get("params")
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise HTTPException(status_code=400, detail="params must be an object")

    material_name = raw.get("material_name", raw.get("ad_name"))
    material_id = raw.get("material_id")
    ad_id = raw.get("ad_id")
    oss_url = raw.get("oss_url")

    if isinstance(material_name, str) and material_name.strip():
        material_name = material_name.strip()
    else:
        material_name = None

    if isinstance(material_id, str) and material_id.strip():
        material_id = material_id.strip()
    elif isinstance(ad_id, str) and ad_id.strip():
        material_id = ad_id.strip()
    else:
        material_id = None

    if not material_name and not material_id:
        raise HTTPException(status_code=400, detail="params.material_name is required for insert_play")

    if isinstance(oss_url, str) and oss_url.strip():
        oss_url = oss_url.strip()
    else:
        oss_url = None

    priority = raw.get("priority", 5)
    if not isinstance(priority, int) or priority < 0 or priority > 9:
        raise HTTPException(status_code=400, detail="params.priority must be integer in [0,9]")

    emergency = raw.get("emergency", raw.get("is_emergency", False))
    if not isinstance(emergency, bool):
        raise HTTPException(status_code=400, detail="params.emergency must be boolean")

    play_mode = raw.get("play_mode", "single")
    if not isinstance(play_mode, str) or not play_mode.strip():
        raise HTTPException(status_code=400, detail="params.play_mode must be non-empty string")

    request_screenshot = raw.get("request_screenshot", True)
    if not isinstance(request_screenshot, bool):
        raise HTTPException(status_code=400, detail="params.request_screenshot must be boolean")

    duration_sec = raw.get("duration_sec")
    if duration_sec is not None:
        if not isinstance(duration_sec, int) or duration_sec <= 0:
            raise HTTPException(status_code=400, detail="params.duration_sec must be positive integer")

    out = {
        "priority": priority,
        "emergency": emergency,
        "is_emergency": emergency,
        "play_mode": play_mode.strip(),
        "request_screenshot": request_screenshot,
    }
    if material_name:
        out["material_name"] = material_name
        out["ad_name"] = material_name
    if material_id:
        out["material_id"] = material_id
    if oss_url:
        out["oss_url"] = oss_url

    if duration_sec is not None:
        out["duration_sec"] = duration_sec

    reason = raw.get("reason")
    if isinstance(reason, str) and reason.strip():
        out["reason"] = reason.strip()

    return out


async def _capture_after_insert_play(device_id: str, cmd_id: str) -> None:
    try:
        snapshot_url = await request_device_snapshot(device_id, timeout=20)
        db_service.update_command_status(
            cmd_id=cmd_id,
            status="success",
            result={
                "insert_play": "completed",
                "snapshot_status": "success",
                "snapshot_url": snapshot_url,
            },
        )
    except Exception as e:
        db_service.update_command_status(
            cmd_id=cmd_id,
            status="success",
            result={
                "insert_play": "completed",
                "snapshot_status": "failed",
                "snapshot_error": str(e),
            },
        )


def _try_parse_json_like(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return value
    if not (text.startswith("{") or text.startswith("[")):
        return value
    try:
        return json.loads(text)
    except Exception:
        return value

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
    action = _normalize_action(payload.get("action"))
    devices = _extract_target_devices(payload)
    device_id = devices[0] if len(devices) == 1 else None
    cmd_id = payload.get("cmd_id") or str(uuid.uuid4())

    if action == "insert_play":
        insert_params = _normalize_insert_play_params(payload)
        batch_id = cmd_id
        send_ts = int(time.time())
        results = []

        for idx, dev_id in enumerate(devices):
            per_cmd_id = cmd_id if len(devices) == 1 else f"{batch_id}:{idx + 1}"
            data = {
                "priority": insert_params["priority"],
                "play_mode": insert_params["play_mode"],
                "is_emergency": insert_params["is_emergency"],
            }
            if "material_id" in insert_params:
                data["material_id"] = insert_params["material_id"]
            if "material_name" in insert_params:
                data["material_name"] = insert_params["material_name"]
                data["ad_name"] = insert_params["material_name"]
            if "oss_url" in insert_params:
                data["oss_url"] = insert_params["oss_url"]
            if "duration_sec" in insert_params:
                data["duration_sec"] = insert_params["duration_sec"]
            if "reason" in insert_params:
                data["reason"] = insert_params["reason"]

            rec = {
                "cmd_id": per_cmd_id,
                "device_id": dev_id,
                "action": "insert_play",
                "status": "pending",
                "send_ts": send_ts,
                "result": {"phase": "validating"},
            }
            params_for_log = {
                **insert_params,
                "batch_id": batch_id,
                "target_size": len(devices),
                "origin_cmd_id": cmd_id,
            }

            try:
                send_remote_command(dev_id, "INSERT_PLAY", data, per_cmd_id)
                rec["status"] = "sent"
                rec["result"] = {
                    "phase": "dispatched",
                    "batch_id": batch_id,
                    "request_screenshot": insert_params["request_screenshot"],
                }
            except Exception as e:
                rec["status"] = "failed"
                rec["result"] = {
                    "phase": "dispatch_failed",
                    "batch_id": batch_id,
                    "error": str(e),
                }

            try:
                db_service.insert_command(
                    {
                        "cmd_id": rec["cmd_id"],
                        "device_id": rec["device_id"],
                        "action": rec["action"],
                        "params": params_for_log,
                        "status": rec["status"],
                        "result": rec["result"],
                        "send_ts": rec["send_ts"],
                    }
                )
            except Exception as e:
                print(f"[insert_play] insert_command failed, fallback to mock: {e}")
                mock_command_db.append({**rec, "params": params_for_log})

            results.append(
                {
                    "device_id": dev_id,
                    "cmd_id": per_cmd_id,
                    "status": rec["status"],
                    "result": rec["result"],
                }
            )

        failed = [x for x in results if x.get("status") == "failed"]
        overall = "success" if len(failed) == 0 else ("failed" if len(failed) == len(results) else "partial")
        return {
            "status": overall,
            "action": "insert_play",
            "cmd_id": cmd_id,
            "batch_id": batch_id,
            "total": len(results),
            "success": len(results) - len(failed),
            "failed": len(failed),
            "items": results,
        }

    if len(devices) != 1:
        raise HTTPException(status_code=400, detail="action only supports one target_device_id; use insert_play for batch")
    
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
    result = _try_parse_json_like(body.get("result"))

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

    # INSERT_PLAY 成功后异步触发截图，增强状态展示能力。
    if updated and cmd_id:
        try:
            row = db_service.get_command_by_cmd_id(cmd_id)
            if row and str(row.get("action") or "").lower() == "insert_play":
                params = row.get("params") or {}
                if isinstance(params, str):
                    params = _try_parse_json_like(params)
                should_capture = isinstance(params, dict) and bool(params.get("request_screenshot", True))
                status_l = str(status or "").lower()
                if should_capture and status_l in {"success", "completed", "done"}:
                    asyncio.create_task(_capture_after_insert_play(device_id or row.get("device_id"), cmd_id))
        except Exception as e:
            print(f"[commands.callback] post-insert capture schedule failed: {e}")

    return {"status": "ok"}


@router.get("/insert-play/{batch_id}")
async def get_insert_play_status(batch_id: str):
    if not isinstance(batch_id, str) or not batch_id.strip():
        raise HTTPException(status_code=400, detail="batch_id is required")

    batch_id = batch_id.strip()
    rows = []
    try:
        rows = db_service.list_commands_by_batch(batch_id=batch_id, action="insert_play", limit=500)
    except Exception as e:
        print(f"[insert_play.status] db query failed, fallback to mock: {e}")

    if not rows:
        rows = []
        for rec in mock_command_db:
            if str(rec.get("action") or "").lower() != "insert_play":
                continue
            params = rec.get("params") or {}
            if isinstance(params, dict) and params.get("batch_id") == batch_id:
                rows.append(rec)

    items = []
    summary = {"pending": 0, "sent": 0, "success": 0, "failed": 0, "timeout": 0, "other": 0}

    for r in rows:
        st = str(r.get("status") or "pending").lower()
        if st in summary:
            summary[st] += 1
        else:
            summary["other"] += 1
        items.append(
            {
                "cmd_id": r.get("cmd_id"),
                "device_id": r.get("device_id"),
                "status": r.get("status"),
                "result": r.get("result"),
                "params": r.get("params"),
                "send_ts": r.get("send_ts"),
                "created_at": r.get("created_at"),
                "updated_at": r.get("updated_at"),
            }
        )

    return {
        "batch_id": batch_id,
        "total": len(items),
        "summary": summary,
        "items": items,
    }
    