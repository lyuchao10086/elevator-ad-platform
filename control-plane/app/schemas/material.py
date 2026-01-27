from pydantic import BaseModel
from typing import Dict,Any,List,Optional

class MaterialMeta(BaseModel):
    material_id: str
    filename: str
    md5: str
    size_bytes: int
    status: str
    created_at: str
    extra: Optional[Dict[str,Any]] = None

class MaterialUploadResponse(BaseModel):
    material_id: str
    filename: str
    md5: str
    status: str = "uploaded" # uploaded / transcoding / done / failed 
    extra: Optional[Dict[str,Any]] = None

class MaterialListResponse(BaseModel):
    total: int
    items: List[MaterialMeta]