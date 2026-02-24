from pydantic import BaseModel
from typing import Any, List, Dict
from datetime import datetime

class CampaignStrategyRequest(BaseModel):
    ads_list: List[Dict[str, Any]]
    devices_list: List[str]
    time_rules: Dict[str, Any]

class CampaignStrategyResponse(BaseModel):
    schedule_id: str
    schedule_config: Dict[str, Any]


from typing import Optional


class CampaignMeta(BaseModel):
    campaign_id: str
    name: Optional[str] = None
    creator_id: Optional[str] = None
    status: Optional[str] = None
    schedule_json: Optional[Dict[str, Any]] = None
    target_device_groups: Optional[Any] = None
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    version: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class CampaignListResponse(BaseModel):
    total: int
    items: List[CampaignMeta]
