from pydantic import BaseModel
from typing import Dict, Any, List, Optional, Literal

class MaterialMeta(BaseModel):
    material_id: str
    filename: str
    md5: str
    size_bytes: int
<<<<<<< HEAD
    status: Literal["uploaded", "transcoding", "done", "failed"]
=======
    status: Literal["uploaded", "transcoding", "done", "failed"]
>>>>>>> 3ec9ac1 (feat(materials): add status flow, callback, and delete)
    created_at: str
    extra: Optional[Dict[str,Any]] = None

class MaterialUploadResponse(BaseModel):
    material_id: str
    filename: str
    md5: str
<<<<<<< HEAD
    status: Literal["uploaded", "transcoding", "done", "failed"] = "uploaded"
=======
    status: Literal["uploaded", "transcoding", "done", "failed"] = "uploaded"
>>>>>>> 3ec9ac1 (feat(materials): add status flow, callback, and delete)
    extra: Optional[Dict[str,Any]] = None

class MaterialListResponse(BaseModel):
    total: int
    items: List[MaterialMeta]


class MaterialStatusPatchRequest(BaseModel):
    status: Literal["uploaded", "transcoding", "done", "failed"]


class MaterialTranscodeCallbackRequest(BaseModel):
    status: Literal["done", "failed"]
    duration: Optional[int] = None
    type: Optional[str] = None
    output_path: Optional[str] = None
    message: Optional[str] = None
    extra: Optional[Dict[str, Any]] = None
