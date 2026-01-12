from pydantic import BaseModel
from typing import Optional

class DeviceRegisterRequest(BaseModel):
    location: Optional[str] = None

class DeviceRegisterResponse(BaseModel):
    device_id: str
    token: str
    location: Optional[str] = None
