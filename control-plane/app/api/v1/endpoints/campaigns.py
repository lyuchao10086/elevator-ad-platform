from fastapi import APIRouter
from app.schemas.campaign import CampaignStrategyRequest, CampaignStrategyResponse

import uuid
from datetime import datetime

router = APIRouter()

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
