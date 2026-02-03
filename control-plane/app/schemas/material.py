from pydantic import BaseModel
from typing import Dict,Any,List,Literal,Optional


MaterialStatus = Literal["uploaded","transcoding","done","failed"]

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

class MaterialStatusPatchRequest(BaseModel):
    status: MaterialStatus