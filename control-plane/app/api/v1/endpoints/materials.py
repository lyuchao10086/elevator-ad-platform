from fastapi import APIRouter, UploadFile, File, Form
from app.schemas.material import MaterialUploadResponse

import hashlib
import uuid

router = APIRouter()

# PR-1：先不做转码，只做“收文件 + 算 md5 + 返回状态”
@router.post("/upload", response_model=MaterialUploadResponse)
async def upload_material(
    file: UploadFile = File(...),
    metadata: str | None = Form(default=None),
):
    content = await file.read()
    md5 = hashlib.md5(content).hexdigest()
    material_id = f"mat_{uuid.uuid4().hex[:8]}"

    # 这里 PR-1 不落盘也行；要落盘的话下次再加 storage/ 目录
    return MaterialUploadResponse(
        material_id=material_id,
        filename=file.filename,
        md5=md5,
        status="PENDING",   # 后续接 Celery 转码后变 READY
        metadata=metadata,
    )
