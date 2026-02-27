import re
import uuid
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from app.schemas.campaigns import (
    CampaignListResponse,
    CampaignStrategyRequest,
    CampaignStrategyResponse,
    ScheduleConfig,
)
from app.services import db_service
from app.services.device_snapshot_service import send_remote_command

router = APIRouter()

_SLOT_PATTERN = re.compile(r"^(?:\*|(?:[01]\d|2[0-3]):[0-5]\d-(?:[01]\d|2[0-3]):[0-5]\d)$")
# In-memory fallback to keep local integration usable when Postgres is unavailable.
_CAMPAIGN_STORE: Dict[str, Dict[str, Any]] = {}


def dt(v: Optional[datetime]):
    return v.isoformat() if isinstance(v, datetime) else v


@router.post("/strategy", response_model=CampaignStrategyResponse)
def create_campaign_strategy(payload: CampaignStrategyRequest):
    campaign_id = f"cmp_{uuid.uuid4().hex[:8]}"
    schedule_id = f"sch_{uuid.uuid4().hex[:8]}"
    version = datetime.utcnow().strftime("%Y%m%d") + "_v1"

    for ad in payload.ads_list:
        invalid_slots = [s for s in ad.slots if not _SLOT_PATTERN.fullmatch(s)]
        if invalid_slots:
            raise HTTPException(
                status_code=400,
                detail=f"invalid slots for ad {ad.id}: {invalid_slots}",
            )

    download_base_url = payload.download_base_url or payload.time_rules.get("download_base_url")
    if not download_base_url:
        download_base_url = "https://oss.aliyun.com/ads/"

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
        # DB is optional for local integration tests; keep memory copy as fallback.
        persisted = False
    _CAMPAIGN_STORE[campaign_id] = campaign_row

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
    try:
        r = db_service.get_campaign(campaign_id)
    except Exception:
        r = None
    if not r:
        r = _CAMPAIGN_STORE.get(campaign_id)
    if not r:
        raise HTTPException(status_code=404, detail="campaign not found")
    return r


@router.post("/{campaign_id}/publish")
def publish_campaign(campaign_id: str):
    mem = _CAMPAIGN_STORE.get(campaign_id)
    if mem:
        mem["status"] = "published"
        mem["updated_at"] = datetime.utcnow().isoformat() + "Z"

    try:
        updated = db_service.update_campaign_status(campaign_id, "published")
    except Exception:
        updated = 0

    campaign = mem
    if not campaign:
        try:
            campaign = db_service.get_campaign(campaign_id)
        except Exception:
            campaign = None
    if not campaign:
        return {"ok": False, "updated": updated, "message": "campaign not found"}

    schedule_json = campaign.get("schedule_json")
    # schedule_json may be stored as text in DB; normalize to dict before push.
    if isinstance(schedule_json, str):
        try:
            schedule_json = json.loads(schedule_json)
        except Exception:
            schedule_json = None
    if not isinstance(schedule_json, dict):
        return {"ok": False, "updated": updated, "message": "invalid schedule_json"}

    target_devices = campaign.get("target_device_groups") or []
    # Accept legacy storage style: single device string.
    if isinstance(target_devices, str):
        target_devices = [target_devices]
    if not isinstance(target_devices, list):
        target_devices = []
    target_devices = [d for d in target_devices if isinstance(d, str) and d.strip()]
    if not target_devices:
        return {"ok": False, "updated": updated, "message": "no target devices"}

    push_result = []
    success_count = 0
    for did in target_devices:
        try:
            # Reuse gateway command channel for schedule delivery.
            send_remote_command(did, "UPDATE_SCHEDULE", schedule_json)
            push_result.append({"device_id": did, "ok": True})
            success_count += 1
        except Exception as e:
            push_result.append({"device_id": did, "ok": False, "error": str(e)})

    ok = success_count > 0
    return {
        "ok": ok,
        "updated": updated,
        "pushed": success_count,
        "total": len(target_devices),
        "results": push_result,
    }
