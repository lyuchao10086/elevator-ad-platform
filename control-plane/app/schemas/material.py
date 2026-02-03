from pydantic import BaseModel
from typing import Dict,Any,List,Literal,Optional
from enum import Enum

class MaterialStatus(str,Enum):
    uploaded = "uploaded"
    transcoding = "transcoding"
    done = "done"
    failed = "failed"

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
    
class MaterialStatusUpdateRequest(BaseModel):
    status: MaterialStatus
    
class MaterialTranscodeCallbackRequest(BaseModel):
    status: Literal["done", "failed"]        # 回调只允许终态
    duration: Optional[int] = None           # 秒
    type: Optional[str] = None               # video/image/pdf...
    output_path: Optional[str] = None        # 转码后文件路径（或对象存储 key）
    message: Optional[str] = None            # 失败原因/说明
    extra: Optional[Dict[str, Any]] = None   # 扩展字段
