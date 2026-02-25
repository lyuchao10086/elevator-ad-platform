from fastapi import APIRouter, UploadFile, File, HTTPException, Form, BackgroundTasks
from app.schemas.material import MaterialUploadResponse
from app.services.material_service import upsert_material, list_materials, get_material, get_material_file_path, delete_material
from app.schemas.material import MaterialListResponse, MaterialMeta
from fastapi.responses import FileResponse, JSONResponse

import hashlib
import uuid
from pathlib import Path
from datetime import datetime, timezone
from app.services import db_service


router = APIRouter()

# PR-2：先落到本地目录，后面再换对象存储/转码队列” 
MATERIAL_DIR = Path("data/materials")
MATERIAL_DIR.mkdir(parents=True,exist_ok=True)


@router.post("/upload", response_model=MaterialUploadResponse)
async def upload_material(
    file: UploadFile = File(...),
    ad_id: str = Form(None),
    advertiser: str = Form(None),
    uploader_id: str = Form(None),
    tags: str = Form(None),
):
    try:
        content = await file.read()
        size_bytes = len(content)
        md5 = hashlib.md5(content).hexdigest()
        # generate sequential material_id where possible
        try:
            from app.services.material_service import get_next_material_id
            material_id = get_next_material_id()
        except Exception:
            material_id = f"mat_{uuid.uuid4().hex[:8]}"

        safe_name = Path(file.filename).name # 防止带路径的filename
        save_path = MATERIAL_DIR / f"{material_id}_{safe_name}"
        save_path.write_bytes(content)
        
        created_at = datetime.now(timezone.utc).isoformat().replace("+00:00","Z")

        # 写索引（最小字段）
        # prefer explicit advertiser field, fall back to legacy ad_id
        chosen_adv = advertiser or ad_id
        meta = {
            "material_id": material_id,
            "advertiser": chosen_adv,
            "ad_id": ad_id,
            "file_name": file.filename,
            "filename": file.filename,
            "md5": md5,
            "size_bytes": size_bytes,
            "status": "uploaded",
            "created_at": created_at,
            "updated_at": created_at,
            "uploader_id": uploader_id,
            "tags": tags.split(',') if tags else [],
            "extra": {"path": str(save_path)}
        }

        upsert_material(meta)
        # try to persist to Postgres if available (best-effort)
        try:
            db_service.insert_material({
                "material_id": meta.get("material_id"),
                "advertiser": meta.get("advertiser"),
                "ad_id": meta.get("ad_id"),
                "file_name": meta.get("file_name"),
                "oss_url": meta.get("oss_url"),
                "md5": meta.get("md5"),
                "type": meta.get("type"),
                "duration_sec": meta.get("duration_sec"),
                "size_bytes": meta.get("size_bytes"),
                "uploader_id": meta.get("uploader_id"),
                "status": meta.get("status"),
                "versions": meta.get("versions"),
                "tags": meta.get("tags"),
                "extra": meta.get("extra"),
                "created_at": meta.get("created_at"),
                "updated_at": meta.get("updated_at"),
            })
        except Exception:
            # don't fail the upload if DB persist fails; keep local index
            import logging
            logging.exception('failed to persist material to DB (best-effort)')

        return MaterialUploadResponse(
            material_id=material_id,
            filename=file.filename,
            md5=md5,
            status="uploaded",
            extra={"path": str(save_path), "size_bytes": size_bytes},
        )
    except Exception as e:
        raise HTTPException(status_code = 500,detail =str(e))

@router.get("/", response_model=MaterialListResponse)
def list_all_materials(offset: int = 0, limit: int = 50):
    # 尝试从 Postgres 读取 materials，失败时回退到本地索引
    try:
        rows = db_service.list_materials(limit=limit, offset=offset)
    except Exception:
        rows = None

    if rows is None:
        raw_items = list_materials(offset=offset, limit=limit)
        # convert local index items to expected keys
        items = []
        for it in raw_items:
            items.append({
                "material_id": it.get("material_id"),
                "advertiser": it.get("advertiser") or it.get("ad_id"),
                "file_name": it.get("file_name") or it.get("filename"),
                "oss_url": (it.get("extra") or {}).get("oss_url") or (it.get("extra") or {}).get("path") or it.get("oss_url"),
                "md5": it.get("md5"),
                "type": it.get("type"),
                "duration_sec": it.get("duration_sec"),
                "size_bytes": it.get("size_bytes") or it.get("size"),
                "uploader_id": it.get("uploader_id"),
                "status": it.get("status"),
                "versions": it.get("versions"),
                "tags": it.get("tags"),
                "created_at": it.get("created_at"),
                "updated_at": it.get("updated_at"),
                "extra": it.get("extra"),
            })
        return {"total": len(items), "items": items}

    # map DB rows -> MaterialMeta fields (Postgres)
    items = []
    for r in rows:
        items.append({
            "material_id": r.get("material_id") or r.get("id"),
            "advertiser": r.get("advertiser") or r.get("ad_id"),
            "file_name": r.get("file_name") or r.get("filename"),
            "oss_url": r.get("oss_url"),
            "md5": r.get("md5"),
            "type": r.get("type"),
            "duration_sec": r.get("duration_sec"),
            "size_bytes": r.get("size_bytes"),
            "uploader_id": r.get("uploader_id"),
            "status": r.get("status"),
            "versions": r.get("versions"),
            "tags": r.get("tags"),
            "created_at": r.get("created_at"),
            "updated_at": r.get("updated_at"),
            "extra": {"oss_url": r.get("oss_url"), "raw": r},
        })

    return {"total": len(items), "items": items}



@router.delete("/{material_id}")
def delete_one_material(material_id: str):
    # try DB delete first
    try:
        # if DB has material, attempt to delete; db_service may raise if not configured
        db_row = db_service.get_material(material_id)
        if db_row:
            # simple deletion; table must support PK material_id
            conn = db_service.get_conn()
            cur = conn.cursor()
            cur.execute("DELETE FROM materials WHERE material_id = %s", [material_id])
            conn.commit()
            cur.close(); conn.close()
    except Exception:
        # ignore DB errors; fall back to local index
        pass

    # remove from local index and disk
    removed = delete_material(material_id)
    if not removed:
        raise HTTPException(status_code=404, detail="material not found")
    return JSONResponse(status_code=200, content={"ok": True})


@router.post("/{material_id}/transcode")
def transcode_material(material_id: str, background_tasks: BackgroundTasks = None):
    # This endpoint will mark material as 'transcoding' and enqueue a background placeholder job.
    item = get_material(material_id)
    if not item:
        raise HTTPException(status_code=404, detail="material not found")

    # mark as transcoding in local index (and DB if available)
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    upsert_material({
        "material_id": material_id,
        "status": "transcoding",
        "updated_at": now,
    })

    # enqueue fake background task to simulate completion (no actual transcode here)
    def _finish():
        upsert_material({
            "material_id": material_id,
            "status": "ready",
            "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        })

    if background_tasks is not None:
        background_tasks.add_task(_finish)

    return JSONResponse(status_code=202, content={"ok": True, "status": "transcoding"})

@router.get("/{material_id}", response_model=MaterialMeta)
def get_one_material(material_id: str):
    item = get_material(material_id)
    if not item:
        raise HTTPException(status_code=404, detail="material not found")

    # normalize keys to match MaterialMeta
    normalized = {
        "material_id": item.get("material_id"),
        "advertiser": item.get("advertiser") or item.get("ad_id"),
        "file_name": item.get("file_name") or item.get("filename"),
        "oss_url": (item.get("extra") or {}).get("oss_url") or item.get("oss_url"),
        "md5": item.get("md5"),
        "type": item.get("type"),
        "duration_sec": item.get("duration_sec"),
        "size_bytes": item.get("size_bytes"),
        "uploader_id": item.get("uploader_id"),
        "status": item.get("status"),
        "versions": item.get("versions"),
        "tags": item.get("tags"),
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
        "extra": item.get("extra"),
    }
    return normalized

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
# @router.patch("/{material_id}/status", response_model=MaterialMeta)
# def patch_material_status(material_id: str, body: MaterialStatusPatchRequest):
#     try:
#         return update_material_status(material_id, body.status)
#     except KeyError:
#         raise HTTPException(status_code=404, detail="material not found")
#     except ValueError as e:
#         raise HTTPException(status_code=400, detail=str(e))
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))

# @router.post("/{material_id}/transcode/callback", response_model=MaterialMeta)
# def transcode_callback(material_id: str, body: MaterialTranscodeCallbackRequest):
#     try:
#         payload = body.model_dump() if hasattr(body, "model_dump") else body.dict()
#         return apply_transcode_callback(material_id, payload)
#     except KeyError:
#         raise HTTPException(status_code=404, detail="material not found")
#     except ValueError as e:
#         raise HTTPException(status_code=400, detail=str(e))
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))
@router.delete("/{material_id}")
def delete_one_material(material_id: str):
    try:
        delete_material(material_id)
        return {"ok": True}
    except KeyError:
        raise HTTPException(status_code=404, detail="material not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
