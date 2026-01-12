from pydantic import BaseModel
from typing import Optional

class MaterialUploadResponse(BaseModel):
    material_id: str
    filename: str
    md5: str
    status: str  # PENDING / READY / FAILED
    metadata: Optional[str] = None
