from pydantic import BaseModel
from typing import Optional, List, Any


class DeviceRegisterRequest(BaseModel):
    device_id: Optional[str] = None
    name: Optional[str] = None
    device_type: Optional[str] = None
    serial_no: Optional[str] = None
    tenant_id: Optional[str] = None
    lon: Optional[float] = None
    lat: Optional[float] = None
    coord_system: Optional[str] = 'WGS84'
    city: Optional[str] = None
    building: Optional[str] = None
    floor: Optional[str] = None
    firmware_version: Optional[str] = None
    mac: Optional[str] = None
    last_seen_ip: Optional[str] = None
    tags: Optional[Any] = None  # accept JSON or list or comma string
    group_id: Optional[str] = None


class DeviceRegisterResponse(BaseModel):
    device_id: str
    token: str
    name: Optional[str] = None
    tenant_id: Optional[str] = None
