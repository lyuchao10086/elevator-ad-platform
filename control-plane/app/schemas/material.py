from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from datetime import datetime


class MaterialMeta(BaseModel):
    material_id: str
    ad_id: Optional[str] = None
    file_name: Optional[str] = None
    oss_url: Optional[str] = None
    md5: Optional[str] = None
    type: Optional[str] = None
    duration_sec: Optional[int] = None
    size_bytes: Optional[int] = None
    uploader_id: Optional[str] = None
    status: Optional[str] = None
    versions: Optional[Any] = None
    tags: Optional[Any] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    extra: Optional[Dict[str, Any]] = None

class MaterialUploadResponse(BaseModel):
    material_id: str
    filename: str
    md5: str
    status: str = "uploaded" # uploaded / transcoding / done / failed 
    extra: Optional[Dict[str,Any]] = None

class MaterialListResponse(BaseModel):
    total: int
    items: List[MaterialMeta]