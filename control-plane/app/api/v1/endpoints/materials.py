from fastapi import APIRouter, UploadFile, File, HTTPException 
from app.schemas.material import MaterialUploadResponse
from app.services.material_service import upsert_material
from app.services.material_service import list_materials,get_material,update_material_status
from app.schemas.material import MaterialListResponse,MaterialMeta,MaterialStatusPatchRequest
from fastapi.responses import FileResponse
from app.services.material_service import get_material_file_path,get_material,update_material_status

import hashlib
import uuid
from pathlib import Path
from datetime import datetime, timezone

from pydantic import BaseModel
from typing import Literal

router = APIRouter()
class MaterialStatusUpdateRequest(BaseModel):
    status: Literal["uploaded","transcoding","done","failed"]

# PR-2：先落到本地目录，后面再换对象存储/转码队列” 
MATERIAL_DIR = Path("data/materials")
MATERIAL_DIR.mkdir(parents=True,exist_ok=True)


@router.post("/upload", response_model=MaterialUploadResponse)
async def upload_material(
    file: UploadFile = File(...)
):
    try:
        content = await file.read()
        size_bytes = len(content)
        md5 = hashlib.md5(content).hexdigest()
        material_id = f"mat_{uuid.uuid4().hex[:8]}"

        safe_name = Path(file.filename).name # 防止带路径的filename
        save_path = MATERIAL_DIR / f"{material_id}_{safe_name}"
        save_path.write_bytes(content)
        
        created_at = datetime.now(timezone.utc).isoformat().replace("+00:00","Z")

        #写索引（最小字段）
        upsert_material({
           "material_id": material_id,
           "filename": file.filename,
           "md5": md5,
           "size_bytes": size_bytes,
           "status": "uploaded",
           "created_at": created_at,
           "extra": {"path": str(save_path)}
        })

        return MaterialUploadResponse(
            material_id=material_id,
            filename=file.filename,
            md5=md5,
            status="uploaded",   
            extra= {"path":str(save_path),
                    "size_bytes": size_bytes},
        )
    except Exception as e:
        raise HTTPException(status_code = 500,detail =str(e))

@router.get("/", response_model=MaterialListResponse)
def list_all_materials(offset: int = 0, limit: int = 50):
    items = list_materials(offset=offset, limit=limit)
    return {"total": len(items), "items": items}

@router.get("/{material_id}", response_model=MaterialMeta)
def get_one_material(material_id: str):
    item = get_material(material_id)
    if not item:
        raise HTTPException(status_code=404, detail="material not found")
    return item

@router.get("/{material_id}/file")
def download_material_file(material_id: str):
    item = get_material(material_id)
    if not item:
        raise HTTPException(status_code=404,detail="material not found")

    p = get_material_file_path(material_id)
    if not p:
        raise HTTPException(status_code=404,detail="material file not found")
        
    # 下载时展示原始文件名(索引中已保存 filename)
    download_name = item.get("filename") or p.name

    return FileResponse(
        path=str(p),
        filename=download_name,
        media_type="application/octet_stream",
    )
    
@router.patch("/{material_id}/status", response_model=MaterialMeta)
def patch_material_status(material_id: str, body: MaterialStatusPatchRequest):
    try:
        return update_material_status(material_id, body.status)
    except KeyError:
        raise HTTPException(status_code=404, detail="material not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
