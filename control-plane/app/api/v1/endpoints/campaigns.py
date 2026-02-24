from fastapi import APIRouter
from app.schemas.campaign import CampaignStrategyRequest, CampaignStrategyResponse
from typing import Optional
import uuid
from datetime import datetime

router = APIRouter()

from typing import List, Dict, Any
from app.services import db_service
from app.schemas.campaign import CampaignListResponse, CampaignMeta
from fastapi import HTTPException

def dt(v: Optional[datetime]):
    return v.isoformat() if isinstance(v, datetime) else None

# PR-1：先做“规则结构化输出”，不做复杂优化算法
@router.post("/strategy", response_model=CampaignStrategyResponse)
def create_campaign_strategy(payload: CampaignStrategyRequest):
    schedule_id = f"sch_{uuid.uuid4().hex[:8]}"

    schedule_config = {
        "schedule_id": schedule_id,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "ads": payload.ads_list,
        "devices": payload.devices_list,
        "time_rules": payload.time_rules,
    }

    return CampaignStrategyResponse(
        schedule_id=schedule_id,
        schedule_config=schedule_config
    )


@router.get("/", response_model=CampaignListResponse)
def list_campaigns(limit: int = 100, offset: int = 0):
    try:
        rows = db_service.list_campaigns(limit=limit, offset=offset)
    except Exception:
        # 如果 DB 不可用，返回空列表以兼容前端
        rows = []

    items: List[Dict[str, Any]] = []
    for r in rows:
        # mapping DB columns to our schema fields
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
        raise HTTPException(status_code=404, detail="campaign not found")
    return r


@router.post("/{campaign_id}/publish")
def publish_campaign(campaign_id: str):
    try:
        updated = db_service.update_campaign_status(campaign_id, 'published')
    except Exception:
        updated = 0
    if updated <= 0:
        # still return success for compatibility (frontend only shows alert)
        return {"ok": False, "updated": updated}
    return {"ok": True, "updated": updated}
