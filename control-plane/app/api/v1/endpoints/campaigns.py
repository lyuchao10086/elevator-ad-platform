import re
import uuid
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from app.core.config import settings
from app.schemas.campaigns import (
    CampaignListResponse,
    CampaignRollbackRequest,
    CampaignStrategyRequest,
    CampaignStrategyResponse,
    ScheduleConfig,
    CampaignVersionListResponse,
)
from app.services import db_service

router = APIRouter()

_SLOT_PATTERN = re.compile(r"^(?:\*|(?:[01]\d|2[0-3]):[0-5]\d-(?:[01]\d|2[0-3]):[0-5]\d)$")
_VERSION_PATTERN = re.compile(r"^(\d{8})_v(\d+)$", re.IGNORECASE)
# In-memory fallback to keep local integration usable when Postgres is unavailable.
_CAMPAIGN_STORE: Dict[str, Dict[str, Any]] = {}
_CAMPAIGN_VERSION_STORE: Dict[str, Dict[str, Dict[str, Any]]] = {}


def dt(v: Optional[datetime]):
    return v.isoformat() if isinstance(v, datetime) else v


def _next_campaign_version(campaign_id: str, current_version: Optional[str] = None) -> str:
    today = datetime.utcnow().strftime("%Y%m%d")
    candidates: List[str] = []
    if isinstance(current_version, str) and current_version:
        candidates.append(current_version)

    try:
        rows = db_service.list_campaign_versions(campaign_id, limit=500, offset=0)
    except Exception:
        rows = None

    if rows:
        for r in rows:
            v = r.get("version")
            if isinstance(v, str) and v:
                candidates.append(v)

    if _fallback_enabled():
        mem_versions = (_CAMPAIGN_VERSION_STORE.get(campaign_id) or {}).keys()
        for v in mem_versions:
            if isinstance(v, str) and v:
                candidates.append(v)

    max_seq = 0
    for v in candidates:
        m = _VERSION_PATTERN.fullmatch(v.strip())
        if not m:
            continue
        if m.group(1) != today:
            continue
        seq = int(m.group(2))
        if seq > max_seq:
            max_seq = seq

    return f"{today}_v{max_seq + 1}"


def _parse_slot_to_range(slot: str) -> Optional[tuple]:
    if slot == "*":
        return (0, 24 * 60)
    if not _SLOT_PATTERN.fullmatch(slot):
        return None
    start, end = slot.split("-")
    sh, sm = start.split(":")
    eh, em = end.split(":")
    start_m = int(sh) * 60 + int(sm)
    end_m = int(eh) * 60 + int(em)
    if end_m <= start_m:
        return None
    return (start_m, end_m)


def _slot_to_edge_time_range(slot: str) -> Optional[str]:
    if slot == "*":
        return "00:00:00-23:59:59"
    parsed = _parse_slot_to_range(slot)
    if not parsed:
        return None
    start, end = slot.split("-")
    return f"{start}:00-{end}:00"


def _has_slot_overlap(ranges: List[tuple]) -> bool:
    if len(ranges) <= 1:
        return False
    ranges = sorted(ranges, key=lambda x: x[0])
    for i in range(1, len(ranges)):
        if ranges[i][0] < ranges[i - 1][1]:
            return True
    return False


def _normalize_schedule_json(schedule_json: Any) -> Optional[Dict[str, Any]]:
    # schedule_json may be stored as text in DB; normalize to dict before push.
    if isinstance(schedule_json, str):
        try:
            schedule_json = json.loads(schedule_json)
        except Exception:
            return None
    if not isinstance(schedule_json, dict):
        return None
    return schedule_json


def _fallback_enabled() -> bool:
    return bool(settings.enable_memory_fallback)


def _normalize_target_devices(raw_devices: Any) -> List[str]:
    if isinstance(raw_devices, str):
        raw_devices = [raw_devices]
    if not isinstance(raw_devices, list):
        return []
    # Keep input order while removing duplicates/empties.
    result: List[str] = []
    seen = set()
    for did in raw_devices:
        if not isinstance(did, str):
            continue
        v = did.strip()
        if not v or v in seen:
            continue
        seen.add(v)
        result.append(v)
    return result


def _build_edge_schedule(schedule_json: Dict[str, Any]) -> Dict[str, Any]:
    version = str(schedule_json.get("version") or datetime.utcnow().strftime("%Y%m%d") + "_v1")
    version_date = version.split("_")[0]
    if len(version_date) == 8 and version_date.isdigit():
        effective_date = f"{version_date[:4]}-{version_date[4:6]}-{version_date[6:]}"
    else:
        effective_date = datetime.utcnow().strftime("%Y-%m-%d")

    suffix = version.split("_", 1)[1].upper() if "_" in version else "V1"
    policy_id = f"POL_SH_{version_date}_{suffix}"

    playlist = schedule_json.get("playlist") or []
    interrupts = schedule_json.get("interrupts") or []
    slot_map: Dict[str, Dict[str, Any]] = {}
    for item in playlist:
        if not isinstance(item, dict):
            continue
        ad_id = item.get("id")
        if not isinstance(ad_id, str) or not ad_id:
            continue
        ad_priority = item.get("priority", 1)
        if not isinstance(ad_priority, int):
            ad_priority = 1
        slots = item.get("slots") or []
        if not isinstance(slots, list):
            continue
        for s in slots:
            if not isinstance(s, str):
                continue
            edge_range = _slot_to_edge_time_range(s)
            if not edge_range:
                continue
            entry = slot_map.setdefault(
                edge_range,
                {
                    "time_range": edge_range,
                    "priority": 1,
                    "volume": 60,
                    "loop_mode": "sequence",
                    "playlist": [],
                },
            )
            if ad_priority > entry["priority"]:
                entry["priority"] = ad_priority
            if edge_range == "00:00:00-23:59:59":
                entry["volume"] = 0
                entry["loop_mode"] = "random"
            if ad_id not in entry["playlist"]:
                entry["playlist"].append(ad_id)

    all_ad_ids: List[str] = []
    for item in playlist:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            ad_id = item["id"]
            if ad_id and ad_id not in all_ad_ids:
                all_ad_ids.append(ad_id)

    fallback_range = "00:00:00-23:59:59"
    # Always provide fallback slot for edge-side default strategy.
    fallback_entry = slot_map.get(
        fallback_range,
        {
            "time_range": fallback_range,
            "priority": 1,
            "volume": 0,
            "loop_mode": "random",
            "playlist": [],
        },
    )
    if not fallback_entry["playlist"]:
        fallback_entry["playlist"] = list(all_ad_ids)
    fallback_entry["priority"] = 1
    fallback_entry["volume"] = 0
    fallback_entry["loop_mode"] = "random"
    slot_map[fallback_range] = fallback_entry

    # Make deterministic output for non-fallback ranges.
    non_fallback_ranges = sorted([k for k in slot_map.keys() if k != fallback_range])
    time_slots = []
    for idx, key in enumerate(non_fallback_ranges, start=1):
        entry = slot_map[key]
        time_slots.append(
            {
                "slot_id": idx,
                "time_range": entry["time_range"],
                "volume": entry["volume"],
                "priority": entry["priority"],
                "loop_mode": entry["loop_mode"],
                "playlist": entry["playlist"],
            }
        )
    time_slots.append(
        {
            "slot_id": 99,
            "time_range": fallback_entry["time_range"],
            "volume": fallback_entry["volume"],
            "priority": fallback_entry["priority"],
            "loop_mode": fallback_entry["loop_mode"],
            "playlist": fallback_entry["playlist"],
        }
    )

    return {
        "policy_id": policy_id,
        "effective_date": effective_date,
        "download_base_url": schedule_json.get("download_base_url") or "https://oss.aliyun.com/ads/",
        "global_config": {
            "default_volume": 60,
            "download_retry_count": 3,
            "report_interval_sec": 60,
        },
        "interrupts": interrupts if isinstance(interrupts, list) else [],
        "time_slots": time_slots,
    }


def _validate_publish_inputs(schedule_json: Dict[str, Any], target_devices: List[str]) -> Dict[str, Any]:
    errors: List[str] = []
    warnings: List[str] = []

    playlist = schedule_json.get("playlist")
    if not isinstance(playlist, list) or not playlist:
        errors.append("playlist is empty")
        return {"ok": False, "errors": errors, "warnings": warnings}

    for idx, item in enumerate(playlist):
        if not isinstance(item, dict):
            errors.append(f"playlist[{idx}] is not an object")
            continue
        for key in ("id", "file", "md5"):
            if not item.get(key):
                errors.append(f"playlist[{idx}] missing {key}")
        priority = item.get("priority")
        if not isinstance(priority, int) or not (1 <= priority <= 100):
            errors.append(f"playlist[{idx}] invalid priority: {priority}")
        slots = item.get("slots")
        if not isinstance(slots, list) or not slots:
            errors.append(f"playlist[{idx}] slots is empty")
            continue
        slot_ranges = []
        seen_slots = set()
        for s in slots:
            if not isinstance(s, str):
                errors.append(f"playlist[{idx}] slot is not a string: {s}")
                continue
            if s in seen_slots:
                errors.append(f"playlist[{idx}] duplicated slot: {s}")
                continue
            seen_slots.add(s)
            parsed = _parse_slot_to_range(s)
            if parsed is None:
                errors.append(f"playlist[{idx}] invalid slot: {s}")
                continue
            if s != "*":
                slot_ranges.append(parsed)
        if "*" in seen_slots and len(seen_slots) > 1:
            errors.append(f"playlist[{idx}] '*' cannot be mixed with other slots")
        if _has_slot_overlap(slot_ranges):
            errors.append(f"playlist[{idx}] slots overlap")

    ids = [str(i.get("id")) for i in playlist if isinstance(i, dict) and i.get("id")]
    if len(ids) != len(set(ids)):
        errors.append("duplicated ad id in playlist")

    if not target_devices:
        errors.append("no target devices")
        return {"ok": False, "errors": errors, "warnings": warnings}

    # DB-backed existence checks (best-effort; no hard fail on DB outage).
    try:
        existing_devices = set(db_service.get_existing_device_ids(target_devices))
        missing_devices = [d for d in target_devices if d not in existing_devices]
        if missing_devices:
            errors.append(f"unknown devices: {missing_devices}")
    except Exception:
        warnings.append("device existence check skipped (db unavailable)")

    try:
        ad_ids = [str(i.get("id")) for i in playlist if isinstance(i, dict) and i.get("id")]
        if ad_ids:
            existing_materials = set(db_service.get_existing_material_ids(ad_ids))
            missing_materials = [m for m in ad_ids if m not in existing_materials]
            if missing_materials:
                errors.append(f"unknown materials: {missing_materials}")
    except Exception:
        warnings.append("material existence check skipped (db unavailable)")

    return {"ok": len(errors) == 0, "errors": errors, "warnings": warnings}


def _save_campaign_version(campaign_id: str, version: str, schedule_json: Dict[str, Any]) -> bool:
    if not version:
        return False
    if _fallback_enabled():
        _CAMPAIGN_VERSION_STORE.setdefault(campaign_id, {})[version] = {
            "campaign_id": campaign_id,
            "version": version,
            "schedule_json": schedule_json,
            "created_at": datetime.utcnow().isoformat() + "Z",
        }
    try:
        db_service.insert_campaign_version(campaign_id, version, schedule_json)
        return True
    except Exception:
        return False


def _get_campaign_or_404(campaign_id: str) -> Dict[str, Any]:
    db_error = False
    try:
        campaign = db_service.get_campaign(campaign_id)
    except Exception:
        campaign = None
        db_error = True
    if not campaign and _fallback_enabled():
        campaign = _CAMPAIGN_STORE.get(campaign_id)
    if not campaign and db_error and not _fallback_enabled():
        raise HTTPException(status_code=503, detail="database unavailable")
    if not campaign:
        raise HTTPException(status_code=404, detail="campaign not found")
    return campaign


def _publish_campaign_pull_mode(
    campaign_id: str,
    campaign: Dict[str, Any],
    schedule_json: Dict[str, Any],
    target_devices: List[str],
    *,
    updated: int = 0,
    idempotent: bool = False,
    message: Optional[str] = None,
    warnings: Optional[List[str]] = None,
) -> Dict[str, Any]:
    response = {
        "ok": True,
        "campaign_id": campaign_id,
        "version": campaign.get("version"),
        "published": True,
        "delivery_mode": "pull",
        "updated": updated,
        "device_count": len(target_devices),
        "material_count": len([item for item in schedule_json.get("playlist") or [] if isinstance(item, dict)]),
    }
    if idempotent:
        response["idempotent"] = True
    if message:
        response["message"] = message
    if warnings:
        response["warnings"] = warnings
    return response


def _mark_campaign_published(campaign_id: str, campaign: Dict[str, Any]) -> int:
    campaign["status"] = "published"
    campaign["updated_at"] = datetime.utcnow().isoformat() + "Z"
    if _fallback_enabled():
        _CAMPAIGN_STORE[campaign_id] = campaign

    try:
        return db_service.update_campaign_status(campaign_id, "published")
    except Exception:
        if not _fallback_enabled():
            raise HTTPException(status_code=503, detail="database unavailable")
        return 0


@router.post("/strategy", response_model=CampaignStrategyResponse)
def create_campaign_strategy(payload: CampaignStrategyRequest):
    campaign_id = f"cmp_{uuid.uuid4().hex[:8]}"
    schedule_id = f"sch_{uuid.uuid4().hex[:8]}"
    version = datetime.utcnow().strftime("%Y%m%d") + "_v1"

    ad_ids = [ad.id for ad in payload.ads_list]
    if len(ad_ids) != len(set(ad_ids)):
        raise HTTPException(status_code=400, detail="duplicated ad id in ads_list")

    for ad in payload.ads_list:
        if not isinstance(ad.priority, int) or not (1 <= ad.priority <= 100):
            raise HTTPException(status_code=400, detail=f"invalid priority for ad {ad.id}: {ad.priority}")
        slot_ranges = []
        seen_slots = set()
        for s in ad.slots:
            if s in seen_slots:
                raise HTTPException(status_code=400, detail=f"duplicated slot for ad {ad.id}: {s}")
            seen_slots.add(s)
            parsed = _parse_slot_to_range(s)
            if parsed is None:
                raise HTTPException(status_code=400, detail=f"invalid slot for ad {ad.id}: {s}")
            if s != "*":
                slot_ranges.append(parsed)
        if "*" in seen_slots and len(seen_slots) > 1:
            raise HTTPException(status_code=400, detail=f"'*' cannot mix with other slots for ad {ad.id}")
        if _has_slot_overlap(slot_ranges):
            raise HTTPException(status_code=400, detail=f"overlapping slots for ad {ad.id}")

    download_base_url = payload.download_base_url or payload.time_rules.get("download_base_url")
    if not download_base_url:
        download_base_url = "https://oss.aliyun.com/ads/"

    interrupts = payload.time_rules.get("interrupts") or []
    if not isinstance(interrupts, list):
        raise HTTPException(status_code=400, detail="time_rules.interrupts must be a list")
    normalized_interrupts = []
    for idx, item in enumerate(interrupts):
        if not isinstance(item, dict):
            raise HTTPException(status_code=400, detail=f"time_rules.interrupts[{idx}] must be an object")
        trigger_type = item.get("trigger_type")
        ad_id = item.get("ad_id")
        priority = item.get("priority")
        play_mode = item.get("play_mode")
        if trigger_type not in {"command", "signal"}:
            raise HTTPException(status_code=400, detail=f"time_rules.interrupts[{idx}] invalid trigger_type")
        if not isinstance(ad_id, str) or not ad_id:
            raise HTTPException(status_code=400, detail=f"time_rules.interrupts[{idx}] invalid ad_id")
        if not isinstance(priority, int) or priority <= 0:
            raise HTTPException(status_code=400, detail=f"time_rules.interrupts[{idx}] invalid priority")
        if not isinstance(play_mode, str) or not play_mode:
            raise HTTPException(status_code=400, detail=f"time_rules.interrupts[{idx}] invalid play_mode")
        normalized_interrupts.append(
            {
                "trigger_type": trigger_type,
                "ad_id": ad_id,
                "priority": priority,
                "play_mode": play_mode,
            }
        )

    schedule_config = ScheduleConfig(
        version=version,
        download_base_url=download_base_url,
        playlist=[
            {
                "id": ad.id,
                "file": ad.file,
                "md5": ad.md5,
                "priority": ad.priority,
                "slots": ad.slots,
            }
            for ad in payload.ads_list
        ],
        interrupts=normalized_interrupts,
    )

    now = datetime.utcnow().isoformat() + "Z"
    campaign_name = payload.time_rules.get("name") or f"strategy_{campaign_id[-4:]}"
    creator_id = payload.time_rules.get("creator_id")
    campaign_row = {
        "campaign_id": campaign_id,
        "name": campaign_name,
        "creator_id": creator_id,
        "status": "draft",
        "schedule_json": schedule_config.model_dump(),
        "target_device_groups": payload.devices_list,
        "start_at": payload.time_rules.get("start_at"),
        "end_at": payload.time_rules.get("end_at"),
        "version": version,
        "created_at": now,
        "updated_at": now,
    }

    persisted = False
    try:
        # Persist draft for publish/list/get lifecycle.
        db_service.insert_campaign(campaign_row)
        persisted = True
    except Exception:
        # DB is optional for local integration tests when fallback is enabled.
        if not _fallback_enabled():
            raise HTTPException(status_code=503, detail="database unavailable")
        persisted = False
    if _fallback_enabled():
        _CAMPAIGN_STORE[campaign_id] = campaign_row
    _save_campaign_version(campaign_id, version, schedule_config.model_dump())

    return CampaignStrategyResponse(
        campaign_id=campaign_id,
        campaign_status="draft",
        persisted=persisted,
        schedule_id=schedule_id,
        schedule_config=schedule_config,
    )


@router.put("/{campaign_id}/strategy", response_model=CampaignStrategyResponse)
def update_campaign_strategy(campaign_id: str, payload: CampaignStrategyRequest):
    db_error = False
    campaign = None
    try:
        campaign = db_service.get_campaign(campaign_id)
    except Exception:
        db_error = True

    if not campaign and _fallback_enabled():
        campaign = _CAMPAIGN_STORE.get(campaign_id)
    if not campaign and db_error and not _fallback_enabled():
        raise HTTPException(status_code=503, detail="database unavailable")
    if not campaign:
        raise HTTPException(status_code=404, detail="campaign not found")

    version = _next_campaign_version(campaign_id, campaign.get("version"))
    schedule_id = f"sch_{uuid.uuid4().hex[:8]}"

    ad_ids = [ad.id for ad in payload.ads_list]
    if len(ad_ids) != len(set(ad_ids)):
        raise HTTPException(status_code=400, detail="duplicated ad id in ads_list")

    for ad in payload.ads_list:
        if not isinstance(ad.priority, int) or not (1 <= ad.priority <= 100):
            raise HTTPException(status_code=400, detail=f"invalid priority for ad {ad.id}: {ad.priority}")
        slot_ranges = []
        seen_slots = set()
        for s in ad.slots:
            if s in seen_slots:
                raise HTTPException(status_code=400, detail=f"duplicated slot for ad {ad.id}: {s}")
            seen_slots.add(s)
            parsed = _parse_slot_to_range(s)
            if parsed is None:
                raise HTTPException(status_code=400, detail=f"invalid slot for ad {ad.id}: {s}")
            if s != "*":
                slot_ranges.append(parsed)
        if "*" in seen_slots and len(seen_slots) > 1:
            raise HTTPException(status_code=400, detail=f"'*' cannot mix with other slots for ad {ad.id}")
        if _has_slot_overlap(slot_ranges):
            raise HTTPException(status_code=400, detail=f"overlapping slots for ad {ad.id}")

    current_schedule = _normalize_schedule_json(campaign.get("schedule_json")) or {}
    download_base_url = payload.download_base_url or payload.time_rules.get("download_base_url")
    if not download_base_url:
        download_base_url = current_schedule.get("download_base_url") or "https://oss.aliyun.com/ads/"

    interrupts = payload.time_rules.get("interrupts") or []
    if not isinstance(interrupts, list):
        raise HTTPException(status_code=400, detail="time_rules.interrupts must be a list")
    normalized_interrupts = []
    for idx, item in enumerate(interrupts):
        if not isinstance(item, dict):
            raise HTTPException(status_code=400, detail=f"time_rules.interrupts[{idx}] must be an object")
        trigger_type = item.get("trigger_type")
        ad_id = item.get("ad_id")
        priority = item.get("priority")
        play_mode = item.get("play_mode")
        if trigger_type not in {"command", "signal"}:
            raise HTTPException(status_code=400, detail=f"time_rules.interrupts[{idx}] invalid trigger_type")
        if not isinstance(ad_id, str) or not ad_id:
            raise HTTPException(status_code=400, detail=f"time_rules.interrupts[{idx}] invalid ad_id")
        if not isinstance(priority, int) or priority <= 0:
            raise HTTPException(status_code=400, detail=f"time_rules.interrupts[{idx}] invalid priority")
        if not isinstance(play_mode, str) or not play_mode:
            raise HTTPException(status_code=400, detail=f"time_rules.interrupts[{idx}] invalid play_mode")
        normalized_interrupts.append(
            {
                "trigger_type": trigger_type,
                "ad_id": ad_id,
                "priority": priority,
                "play_mode": play_mode,
            }
        )

    schedule_config = ScheduleConfig(
        version=version,
        download_base_url=download_base_url,
        playlist=[
            {
                "id": ad.id,
                "file": ad.file,
                "md5": ad.md5,
                "priority": ad.priority,
                "slots": ad.slots,
            }
            for ad in payload.ads_list
        ],
        interrupts=normalized_interrupts,
    )

    now = datetime.utcnow().isoformat() + "Z"
    campaign_name = payload.time_rules.get("name") or campaign.get("name")
    modifier_id = payload.time_rules.get("creator_id")

    updated_row = {
        "campaign_id": campaign_id,
        "name": campaign_name,
        "creator_id": modifier_id or campaign.get("creator_id"),
        "status": "draft",
        "schedule_json": schedule_config.model_dump(),
        "target_device_groups": payload.devices_list,
        "start_at": payload.time_rules.get("start_at") or campaign.get("start_at"),
        "end_at": payload.time_rules.get("end_at") or campaign.get("end_at"),
        "version": version,
        "created_at": campaign.get("created_at") or now,
        "updated_at": now,
    }

    persisted = False
    try:
        db_service.insert_campaign(updated_row)
        persisted = True
    except Exception:
        if not _fallback_enabled():
            raise HTTPException(status_code=503, detail="database unavailable")
        persisted = False

    if _fallback_enabled():
        _CAMPAIGN_STORE[campaign_id] = updated_row
    _save_campaign_version(campaign_id, version, schedule_config.model_dump())

    return CampaignStrategyResponse(
        campaign_id=campaign_id,
        campaign_status="draft",
        persisted=persisted,
        schedule_id=schedule_id,
        schedule_config=schedule_config,
    )


@router.get("/", response_model=CampaignListResponse)
def list_campaigns(limit: int = 100, offset: int = 0):
    try:
        rows = db_service.list_campaigns(limit=limit, offset=offset)
    except Exception:
        rows = None

    if rows is None:
        if not _fallback_enabled():
            raise HTTPException(status_code=503, detail="database unavailable")
        # Fallback path used in local dev when DB is not configured.
        mem_items = list(_CAMPAIGN_STORE.values())
        items = []
        for r in mem_items[offset:offset + limit]:
            items.append({
                "campaign_id": r.get("campaign_id"),
                "name": r.get("name"),
                "creator_id": r.get("creator_id"),
                "status": r.get("status"),
                "schedule_json": r.get("schedule_json"),
                "target_device_groups": r.get("target_device_groups"),
                "start_at": dt(r.get("start_at")),
                "end_at": dt(r.get("end_at")),
                "version": r.get("version"),
                "created_at": dt(r.get("created_at")),
                "updated_at": dt(r.get("updated_at")),
            })
        return {"total": len(mem_items), "items": items}

    items: List[Dict[str, Any]] = []
    for r in rows:
        items.append({
            "campaign_id": r.get("campaign_id") or r.get("id"),
            "name": r.get("name"),
            "creator_id": r.get("creator_id"),
            "status": r.get("status"),
            "schedule_json": r.get("schedule_json"),
            "target_device_groups": r.get("target_device_groups"),
            "start_at": dt(r.get("start_at")),
            "end_at": dt(r.get("end_at")),
            "version": r.get("version"),
            "created_at": dt(r.get("created_at")),
            "updated_at": dt(r.get("updated_at")),
        })
    return {"total": len(items), "items": items}


@router.get("/{campaign_id}")
def get_campaign(campaign_id: str):
    db_error = False
    try:
        r = db_service.get_campaign(campaign_id)
    except Exception:
        r = None
        db_error = True
    if not r and _fallback_enabled():
        r = _CAMPAIGN_STORE.get(campaign_id)
    if not r and db_error and not _fallback_enabled():
        raise HTTPException(status_code=503, detail="database unavailable")
    if not r:
        raise HTTPException(status_code=404, detail="campaign not found")
    return r


@router.delete("/{campaign_id}")
def delete_campaign(campaign_id: str):
    deleted = 0
    db_error = False
    try:
        deleted = db_service.delete_campaign(campaign_id)
    except Exception:
        db_error = True
        deleted = 0

    removed_mem = False
    if _fallback_enabled():
        removed_mem = _CAMPAIGN_STORE.pop(campaign_id, None) is not None
        _CAMPAIGN_VERSION_STORE.pop(campaign_id, None)

    if deleted < 1 and not removed_mem and db_error and not _fallback_enabled():
        raise HTTPException(status_code=503, detail="database unavailable")

    if deleted < 1 and not removed_mem:
        raise HTTPException(status_code=404, detail="campaign not found")

    return {"ok": True, "deleted": 1}


@router.get("/{campaign_id}/schedule-config")
def get_campaign_schedule_config(campaign_id: str):
    """
    Export pure schedule_config JSON for edge-side schedule.json consumption.
    """
    db_error = False
    try:
        campaign = db_service.get_campaign(campaign_id)
    except Exception:
        campaign = None
        db_error = True

    if not campaign and _fallback_enabled():
        campaign = _CAMPAIGN_STORE.get(campaign_id)
    if not campaign and db_error and not _fallback_enabled():
        raise HTTPException(status_code=503, detail="database unavailable")
    if not campaign:
        raise HTTPException(status_code=404, detail="campaign not found")

    schedule_json = _normalize_schedule_json(campaign.get("schedule_json"))
    if not schedule_json:
        raise HTTPException(status_code=400, detail="invalid schedule_json")

    return schedule_json


@router.get("/{campaign_id}/edge-schedule")
def get_campaign_edge_schedule(campaign_id: str):
    """
    Export edge-consumable schedule JSON for terminal SyncSchedule().
    """
    db_error = False
    try:
        campaign = db_service.get_campaign(campaign_id)
    except Exception:
        campaign = None
        db_error = True

    if not campaign and _fallback_enabled():
        campaign = _CAMPAIGN_STORE.get(campaign_id)
    if not campaign and db_error and not _fallback_enabled():
        raise HTTPException(status_code=503, detail="database unavailable")
    if not campaign:
        raise HTTPException(status_code=404, detail="campaign not found")

    schedule_json = _normalize_schedule_json(campaign.get("schedule_json"))
    if not schedule_json:
        raise HTTPException(status_code=400, detail="invalid schedule_json")
    return _build_edge_schedule(schedule_json)


@router.get("/{campaign_id}/publish-logs")
def get_campaign_publish_logs(campaign_id: str, limit: int = 100, offset: int = 0):
    _get_campaign_or_404(campaign_id)
    return {
        "campaign_id": campaign_id,
        "delivery_mode": "pull",
        "deprecated": True,
        "total": 0,
        "success": 0,
        "failed": 0,
        "items": [],
        "limit": limit,
        "offset": offset,
        "message": "publish logs are unavailable in pull delivery mode",
    }


@router.post("/{campaign_id}/publish")
def publish_campaign(campaign_id: str):
    campaign = _get_campaign_or_404(campaign_id)

    schedule_json = _normalize_schedule_json(campaign.get("schedule_json"))
    if not schedule_json:
        raise HTTPException(status_code=400, detail="invalid schedule_json")

    target_devices = _normalize_target_devices(campaign.get("target_device_groups") or [])
    validation = _validate_publish_inputs(schedule_json, target_devices)
    if not validation["ok"]:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "publish validation failed",
                "errors": validation["errors"],
                "warnings": validation["warnings"],
            },
        )
    _save_campaign_version(campaign_id, campaign.get("version"), schedule_json)

    if campaign.get("status") == "published":
        return _publish_campaign_pull_mode(
            campaign_id,
            campaign,
            schedule_json,
            target_devices,
            updated=0,
            idempotent=True,
            message="already published in pull delivery mode",
            warnings=validation["warnings"],
        )

    updated = _mark_campaign_published(campaign_id, campaign)
    return _publish_campaign_pull_mode(
        campaign_id,
        campaign,
        schedule_json,
        target_devices,
        updated=updated,
        warnings=validation["warnings"],
    )


@router.get("/{campaign_id}/versions", response_model=CampaignVersionListResponse)
def list_versions(campaign_id: str, limit: int = 50, offset: int = 0):
    try:
        rows = db_service.list_campaign_versions(campaign_id, limit=limit, offset=offset)
    except Exception:
        rows = None

    if rows is None:
        if not _fallback_enabled():
            raise HTTPException(status_code=503, detail="database unavailable")
        mem = list((_CAMPAIGN_VERSION_STORE.get(campaign_id) or {}).values())
        mem.sort(key=lambda x: x.get("created_at") or "", reverse=True)
        items = mem[offset:offset + limit]
        return {"total": len(mem), "items": items}

    return {"total": len(rows), "items": rows}


@router.post("/{campaign_id}/retry-failed")
def retry_failed_devices(campaign_id: str):
    _get_campaign_or_404(campaign_id)
    return {
        "ok": True,
        "campaign_id": campaign_id,
        "delivery_mode": "pull",
        "retried": 0,
        "deprecated": True,
        "message": "retry-failed is not applicable in pull delivery mode",
    }


@router.post("/{campaign_id}/rollback")
def rollback_campaign(campaign_id: str, body: CampaignRollbackRequest):
    version = body.version
    version_row = None
    try:
        version_row = db_service.get_campaign_version(campaign_id, version)
    except Exception:
        if not _fallback_enabled():
            raise HTTPException(status_code=503, detail="database unavailable")
        version_row = None
    if not version_row and _fallback_enabled():
        version_row = (_CAMPAIGN_VERSION_STORE.get(campaign_id) or {}).get(version)
    if not version_row:
        raise HTTPException(status_code=404, detail="campaign version not found")

    schedule_json = _normalize_schedule_json(version_row.get("schedule_json"))
    if not schedule_json:
        raise HTTPException(status_code=400, detail="invalid campaign version schedule")

    campaign = _get_campaign_or_404(campaign_id)
    target_devices = _normalize_target_devices(campaign.get("target_device_groups") or [])

    if body.publish_now and campaign.get("status") == "published" and campaign.get("version") == version:
        validation = _validate_publish_inputs(schedule_json, target_devices)
        if not validation["ok"]:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "rollback publish validation failed",
                    "errors": validation["errors"],
                    "warnings": validation["warnings"],
                },
            )
        return _publish_campaign_pull_mode(
            campaign_id,
            campaign,
            schedule_json,
            target_devices,
            updated=0,
            idempotent=True,
            message="rollback version already published in pull delivery mode",
            warnings=validation["warnings"],
        )

    campaign["schedule_json"] = schedule_json
    campaign["version"] = version
    campaign["status"] = "draft"
    campaign["updated_at"] = datetime.utcnow().isoformat() + "Z"
    if _fallback_enabled():
        _CAMPAIGN_STORE[campaign_id] = campaign
    try:
        db_service.insert_campaign(campaign)
    except Exception:
        pass

    if not body.publish_now:
        return {
            "ok": True,
            "campaign_id": campaign_id,
            "version": version,
            "published": False,
            "delivery_mode": "pull",
        }

    validation = _validate_publish_inputs(schedule_json, target_devices)
    if not validation["ok"]:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "rollback publish validation failed",
                "errors": validation["errors"],
                "warnings": validation["warnings"],
            },
        )

    updated = _mark_campaign_published(campaign_id, campaign)
    return _publish_campaign_pull_mode(
        campaign_id,
        campaign,
        schedule_json,
        target_devices,
        updated=updated,
        warnings=validation["warnings"],
    )
