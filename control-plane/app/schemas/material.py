from pydantic import BaseModel
from typing import Dict,Any,List,Optional
from typing import Literal

MaterialStatus = Literal["uploaded","transcoding","done"]

class MaterialMeta(BaseModel):
    material_id: str
    filename: str
    md5: str
    size_bytes: int
    status: MaterialStatus
    created_at: str
    extra: Optional[Dict[str,Any]] = None

class MaterialUploadResponse(BaseModel):
    material_id: str
    filename: str
    md5: str
    status: MaterialStatus
    extra: Optional[Dict[str,Any]] = None

class MaterialListResponse(BaseModel):
    total: int
    items: List[MaterialMeta]