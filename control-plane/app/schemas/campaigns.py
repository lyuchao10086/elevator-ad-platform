from pydantic import BaseModel
from typing import Any, List, Dict, Literal, Optional
from datetime import datetime


class CampaignAdItem(BaseModel):
    id: str
    file: str
    md5: str
    priority: int
    slots: List[str]


class SchedulePlaylistItem(BaseModel):
    id: str
    file: str
    md5: str
    priority: int
    slots: List[str]


class ScheduleConfig(BaseModel):
    type: Literal["schedule_update"] = "schedule_update"
    version: str
    download_base_url: str
    playlist: List[SchedulePlaylistItem]


class CampaignStrategyRequest(BaseModel):
    ads_list: List[CampaignAdItem]
    devices_list: List[str]
    time_rules: Dict[str, Any]
    download_base_url: Optional[str] = None

class CampaignStrategyResponse(BaseModel):
    schedule_id: str
    schedule_config: ScheduleConfig


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
