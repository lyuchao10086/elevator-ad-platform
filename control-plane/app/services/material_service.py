# app/services/material_index.py
import json
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

MATERIAL_DIR = Path("data/materials")
INDEX_PATH = MATERIAL_DIR / "index.json"

_LOCK = threading.Lock()


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
