from datetime import datetime
from typing import Any, Dict, List, Optional, Literal

from pydantic import BaseModel, Field

class MaterialMeta(BaseModel):
    material_id: str
    advertiser: Optional[str] = None
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
    status: str = "uploaded"  # uploaded / transcoding / done / failed
    extra: Optional[Dict[str, Any]] = None

class MaterialListResponse(BaseModel):
    total: int
    items: List[MaterialMeta]

class MaterialTranscodeCallbackRequest(BaseModel):
    status: Literal["done", "failed"] = Field(..., examples=["done"])
    duration: Optional[int] = Field(default=None, examples=[15])
    type: Optional[str] = Field(default=None, examples=["pdf"])
    output_path: Optional[str] = Field(
        default=None,
        examples=["oss://bucket/materials/mat_xxx_light.pdf"],
    )
    message: Optional[str] = Field(default=None, examples=["transcode success"])
    extra: Optional[Dict[str, Any]] = Field(
        default=None,
        examples=[{"codec": "h264", "bitrate": "1500k"}],
    )
