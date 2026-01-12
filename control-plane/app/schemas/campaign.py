from pydantic import BaseModel
from typing import Any, List, Dict

class CampaignStrategyRequest(BaseModel):
    ads_list: List[Dict[str, Any]]
    devices_list: List[str]
    time_rules: Dict[str, Any]

class CampaignStrategyResponse(BaseModel):
    schedule_id: str
    schedule_config: Dict[str, Any]
