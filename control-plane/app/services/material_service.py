# app/services/material_index.py
import json
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional
import re

def get_next_material_id(prefix_hint: Optional[str] = None, pad: int = 3) -> str:
    """
    Generate a new sequential material_id based on existing IDs.
    Strategy:
    - Collect ids from local index and (best-effort) Postgres via db_service.
    - Detect ids that end with a numeric suffix like 'M_001' or 'mat001'.
    - Choose a prefix (either prefix_hint if present, or the most common detected prefix, or 'M').
    - Return prefix + '_' + zero-padded number using detected width or provided pad.
    """
    # collect ids from local index
    data = _read_index()
    items = data.get('items', [])
    ids = [it.get('material_id') for it in items if it.get('material_id')]

    # try to get ids from DB if available
    try:
        from app.services import db_service
        try:
            rows = db_service.list_materials(limit=10000, offset=0)
            for r in rows:
                mid = r.get('material_id') or r.get('id')
                if mid:
                    ids.append(mid)
        except Exception:
            # ignore DB errors
            pass
    except Exception:
        pass

    # parse ids for prefix+number
    pattern = re.compile(r'^([A-Za-z]+)[-_]?(0*)(\d+)$')
    prefix_counts = {}
    nums_by_prefix = {}
    widths = {}
    for mid in ids:
        if not isinstance(mid, str):
            continue
        m = pattern.match(mid)
        if m:
            p = m.group(1)
            num_str = m.group(3)
            num = int(num_str)
            prefix_counts[p] = prefix_counts.get(p, 0) + 1
            nums_by_prefix.setdefault(p, []).append(num)
            widths[p] = max(widths.get(p, 0), len(num_str))

    # choose prefix
    chosen = None
    if prefix_hint:
        # normalize hint (keep only letters)
        ph = re.sub(r'[^A-Za-z]', '', prefix_hint) or prefix_hint
        if ph in nums_by_prefix:
            chosen = ph
        else:
            chosen = ph
    if chosen is None:
        if prefix_counts:
            # pick most common prefix
            chosen = max(prefix_counts.items(), key=lambda kv: kv[1])[0]
        else:
            chosen = 'M'

    # determine next number
    existing_nums = nums_by_prefix.get(chosen, [])
    next_num = (max(existing_nums) + 1) if existing_nums else 1
    width = widths.get(chosen, pad)

    # format as PREFIX_001
    candidate = f"{chosen}_{str(next_num).zfill(width)}"
    # ensure uniqueness
    existing_set = set([i for i in ids if isinstance(i, str)])
    while candidate in existing_set:
        next_num += 1
        candidate = f"{chosen}_{str(next_num).zfill(width)}"

    return candidate

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


def delete_material(material_id: str) -> bool:
    """
    Delete material from local index and remove file if present. Returns True if removed.
    """
    # read item first
    item = None
    with _LOCK:
        data = _read_index()
        items: List[Dict[str, Any]] = data.get("items", [])
        for it in items:
            if it.get("material_id") == material_id:
                item = it
                break
        new_items = [it for it in items if it.get("material_id") != material_id]
        if len(new_items) == len(items):
            return False
        # update index
        data["items"] = new_items
        _atomic_write(data)

    # attempt to remove file on disk (best-effort)
    try:
        if item:
            extra = item.get('extra') or {}
            path_str = extra.get('path')
            if path_str:
                p = Path(path_str)
                if p.exists() and p.is_file():
                    try:
                        p.unlink()
                    except Exception:
                        pass
    except Exception:
        pass

    return True


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