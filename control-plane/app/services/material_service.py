# app/services/material_index.py
import json
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional
from typing import Literal
from datetime import datetime,timezone

MATERIAL_DIR = Path("data/materials")
INDEX_PATH = MATERIAL_DIR / "index.json"

MaterialStatus = Literal["uploaded","transcoding","done,","failed"]
_LOCK = threading.Lock()

_ALLOWED_STATUSES = {"uploaded","transcoding","done","failed"}

ALLOWED_TRANSITIONS = {
    "uploaded": {"transcoding"},
    "transcoding": {"done", "failed"},
    "done": set(),      # 如果允许 done -> transcoding，就加上 {"transcoding"}
    "failed": {"transcoding"},  # 可选：失败后允许重试转码
}

def _ensure_paths():
    MATERIAL_DIR.mkdir(parents=True, exist_ok=True)
    if not INDEX_PATH.exists():
        # 初始化空索引
        INDEX_PATH.write_text(json.dumps({"items": []}, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_index() -> Dict[str, Any]:
    _ensure_paths()
    raw = INDEX_PATH.read_text(encoding="utf-8").strip()
    if not raw:
        return {"items": []}
    return json.loads(raw)


def _atomic_write(data: Dict[str, Any]) -> None:
    _ensure_paths()
    tmp = INDEX_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, INDEX_PATH)  # 原子替换


def upsert_material(meta: Dict[str, Any]) -> None:
    """
    meta 至少包含 material_id
    """
    with _LOCK:
        data = _read_index()
        items: List[Dict[str, Any]] = data.get("items", [])

        mid = meta["material_id"]
        found = False
        for i, it in enumerate(items):
            if it.get("material_id") == mid:
                items[i] = {**it, **meta}
                found = True
                break
        if not found:
            items.insert(0, meta)  # 新的放前面

        data["items"] = items
        _atomic_write(data)

def update_material_status(material_id: str, new_status: str) -> Dict[str, Any]:
    with _LOCK:
        data = _read_index()
        items = data.get("items", [])
        for i, it in enumerate(items):
            if it.get("material_id") == material_id:
                old = it.get("status")
                if old is None:
                    old = "uploaded"

                allowed = ALLOWED_TRANSITIONS.get(old, set())
                if new_status not in allowed and new_status != old:
                    raise ValueError(f"invalid status transition: {old} -> {new_status}")

                it["status"] = new_status
                items[i] = it
                data["items"] = items
                _atomic_write(data)
                return it

    raise KeyError("material not found")


def apply_transcode_callback(material_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    转码服务回调：将素材状态更新为 done/failed，并写入转码产物信息到 extra
    payload 形如：
      {
        "status": "done" | "failed",
        "duration": 15,
        "type": "video",
        "output_path": "...",
        "message": "...",
        "extra": {...}
      }
    """
    item = get_material(material_id)
    if not item:
        raise KeyError("material not found")

    new_status = payload.get("status")
    if new_status is None:
        raise ValueError("missing status")

    # 复用你的状态机校验（应要求 transcoding -> done/failed）
    updated = update_material_status(material_id, new_status)

    # 合并额外信息
    extra = updated.get("extra") or {}

    if payload.get("duration") is not None:
        extra["duration"] = payload["duration"]
    if payload.get("type") is not None:
        extra["type"] = payload["type"]
    if payload.get("output_path") is not None:
        extra["output_path"] = payload["output_path"]
    if payload.get("message") is not None:
        extra["transcode_message"] = payload["message"]

    payload_extra = payload.get("extra")
    if isinstance(payload_extra, dict):
        extra.update(payload_extra)

    updated["extra"] = extra
    upsert_material(updated)
    return updated


def get_material(material_id: str) -> Optional[Dict[str, Any]]:
    with _LOCK:
        data = _read_index()
        for it in data.get("items", []):
            if it.get("material_id") == material_id:
                return it
    return None


def list_materials(offset: int = 0, limit: int = 50) -> List[Dict[str, Any]]:
    with _LOCK:
        data = _read_index()
        items = data.get("items", [])
        return items[offset : offset + limit]

def get_material_file_path(material_id: str) -> Optional[Path]:
    item = get_material(material_id)
    if not item:
        return None

    extra = item.get("extra") or {}
    path_str = extra.get("path")
    if not path_str:
        return None
    
    p = Path(path_str)

    # 安全校验：必须在MATERIAL_DIR 目录里(防止 ../ 任意文件下载)
    try:
        if MATERIAL_DIR.resolve() not in p.resolve().parents and p.resolve() != MATERIAL_DIR.resolve:
            return None
    except Exception:
        return None
    
    if not p.exists() or not p.is_file():
        return None
    
    return p