from fastapi import APIRouter, UploadFile, File, HTTPException, Form, BackgroundTasks
from app.schemas.material import MaterialUploadResponse
from app.services.material_service import upsert_material, list_materials, get_material, get_material_file_path, delete_material
from app.schemas.material import MaterialListResponse, MaterialMeta
from fastapi.responses import FileResponse, JSONResponse

import hashlib
import uuid
import os
import mimetypes
from pathlib import Path
from datetime import datetime, timezone
from app.services import db_service


router = APIRouter()

# 素材文件先落到本地磁盘，再写入本地索引；如数据库可用，则补做一次
# best-effort 持久化，保证开发环境和联调环境都能工作。
MATERIAL_DIR = Path("data/materials")
MATERIAL_DIR.mkdir(parents=True,exist_ok=True)
_ENV_LOADED = False
_ENV_SOURCE = None


def _load_control_plane_env_once():
    """Best-effort .env loader for this module to avoid startup cwd dependency."""
    global _ENV_LOADED, _ENV_SOURCE
    if _ENV_LOADED:
        return
    try:
        base_dir = Path(__file__).resolve().parents[4]  # control-plane/
        env_candidates = [base_dir / ".env", base_dir / ".env.example"]
        for env_path in env_candidates:
            if not env_path.exists():
                continue
            _ENV_SOURCE = str(env_path)
            with env_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    if k and (k not in os.environ):
                        os.environ[k] = v
    except Exception:
        # keep upload path robust; missing env file should be surfaced by credential checks later
        pass
    finally:
        _ENV_LOADED = True


def _first_env(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name)
        if value is not None and str(value).strip() != "":
            return str(value).strip()
    return default


def _upload_to_aliyun_oss(filename: str, content: bytes, content_type: str = None):
    """Upload bytes to Aliyun OSS and return (public_url, object_key)."""
    _load_control_plane_env_once()
    try:
        import oss2
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"oss sdk unavailable: {e}")

    access_key_id = _first_env("ALIYUN_OSS_ACCESS_KEY_ID", "OSS_ACCESS_KEY_ID", "OSS_ACCESS_KEY")
    access_key_secret = _first_env("ALIYUN_OSS_ACCESS_KEY_SECRET", "OSS_SECRET_ACCESS_KEY", "OSS_SECRET_KEY")
    bucket_name = _first_env("ALIYUN_OSS_BUCKET", "OSS_BUCKET", default="bucket-elevator")
    endpoint = _first_env("ALIYUN_OSS_ENDPOINT", "OSS_ENDPOINT", default="oss-cn-hangzhou.aliyuncs.com")
    prefix = _first_env("ALIYUN_OSS_OBJECT_PREFIX", "OSS_OBJECT_PREFIX", default="ads").strip("/")

    if not access_key_id or not access_key_secret:
        source = _ENV_SOURCE or "process environment"
        raise HTTPException(
            status_code=500,
            detail=(
                "missing OSS credentials: set ALIYUN_OSS_ACCESS_KEY_ID/ALIYUN_OSS_ACCESS_KEY_SECRET "
                "or OSS_ACCESS_KEY/OSS_SECRET_KEY; "
                f"loaded_from={source}; "
                f"ak_present={bool(_first_env('ALIYUN_OSS_ACCESS_KEY_ID', 'OSS_ACCESS_KEY_ID', 'OSS_ACCESS_KEY'))}; "
                f"sk_present={bool(_first_env('ALIYUN_OSS_ACCESS_KEY_SECRET', 'OSS_SECRET_ACCESS_KEY', 'OSS_SECRET_KEY'))}"
            ),
        )

    endpoint_url = endpoint if endpoint.startswith("http://") or endpoint.startswith("https://") else f"https://{endpoint}"
    public_base = _first_env("ALIYUN_OSS_PUBLIC_BASE_URL", "OSS_PUBLIC_BASE_URL", default=f"https://{bucket_name}.{endpoint}").rstrip("/")

    safe_name = Path(filename or "material.bin").name
    object_key = f"{prefix}/{safe_name}" if prefix else safe_name

    auth = oss2.Auth(access_key_id, access_key_secret)
    bucket = oss2.Bucket(auth, endpoint_url, bucket_name)

    headers = {}
    if content_type:
        headers["Content-Type"] = content_type
    result = bucket.put_object(object_key, content, headers=headers or None)
    status = getattr(result, "status", None)
    if status is None or status < 200 or status >= 300:
        raise HTTPException(status_code=500, detail=f"upload to OSS failed, status={status}")

    return f"{public_base}/{object_key}", object_key


@router.post("/upload", response_model=MaterialUploadResponse)
# 上传流程分三步：
# 1) 二进制文件写入本地目录；
# 2) 更新本地 JSON 索引；
# 3) 尝试同步到 Postgres，但数据库失败不阻塞上传。
async def upload_material(
    file: UploadFile = File(None),
    ad_id: str = Form(None),
    advertiser: str = Form(None),
    uploader_id: str = Form(None),
    tags: str = Form(None),
    type: str = Form(None),
    duration_sec: int = Form(None),
    file_name: str = Form(None),
):
    try:
        if file is None:
            raise HTTPException(status_code=400, detail="missing file")

        content = b""
        size_bytes = 0
        md5 = ""
        # 优先生成可读的顺序 ID，便于 Swagger、文件目录和数据库排查。
        # 如果推断失败，再回退到 UUID。
        try:
            from app.services.material_service import get_next_material_id
            material_id = get_next_material_id()
        except Exception:
            material_id = f"mat_{uuid.uuid4().hex[:8]}"

        save_path = None
        resolved_filename = file_name
        oss_url = None
        oss_object_key = None
        if file is not None:
            content = await file.read()
            size_bytes = len(content)
            md5 = hashlib.md5(content).hexdigest()

            # 去掉用户上传文件名里可能携带的路径信息，只保留文件名本身。
            resolved_filename = resolved_filename or file.filename or f"{material_id}.bin"
            safe_name = Path(resolved_filename).name
            save_path = MATERIAL_DIR / f"{material_id}_{safe_name}"
            save_path.write_bytes(content)

            # 自动上传 OSS 并生成可访问的 oss_url。
            guessed_content_type = file.content_type or mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
            oss_url, oss_object_key = _upload_to_aliyun_oss(safe_name, content, guessed_content_type)
        
        created_at = datetime.now(timezone.utc).isoformat().replace("+00:00","Z")

        # 写索引（最小字段）
        # prefer explicit advertiser field, fall back to legacy ad_id
        chosen_adv = advertiser or ad_id
        meta = {
            "material_id": material_id,
            "advertiser": chosen_adv,
            "ad_id": ad_id,
            "file_name": resolved_filename,
            "filename": resolved_filename,
            "oss_url": oss_url,
            "md5": md5,
            "type": type,
            "duration_sec": duration_sec,
            "size_bytes": size_bytes,
            "status": "uploaded",
            "created_at": created_at,
            "updated_at": created_at,
            "uploader_id": uploader_id,
            "tags": tags.split(',') if tags else [],
            "extra": {
                "path": str(save_path) if save_path else None,
                "oss_url": oss_url,
                "oss_object_key": oss_object_key,
            }
        }

        upsert_material(meta)
        # 数据库持久化主要服务于查询和管理；素材文件管理本身仍以本地索引
        # 为兜底，避免数据库短暂不可用时上传链路直接失败。
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
            filename=resolved_filename,
            md5=md5,
            status="uploaded",
            extra={
                "path": str(save_path) if save_path else None,
                "size_bytes": size_bytes,
                "oss_url": oss_url,
                "oss_object_key": oss_object_key,
            },
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
        # 把本地索引记录统一转换成 MaterialMeta 响应结构，调用方不需要关心
        # 当前数据来自 DB 还是本地索引。
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

    # 把 DB 行数据也转换成同一套 MaterialMeta 结构，保持接口返回稳定。
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
    # 删除时优先清理 DB 元数据，再删除本地索引和物理文件，尽量保持元数据
    # 与磁盘状态一致。
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
    # 这里先保留一个“伪转码”入口，核心作用是把状态流转跑通，方便前端和
    # 联调验证；后续再替换成真实转码任务。
    item = get_material(material_id)
    if not item:
        raise HTTPException(status_code=404, detail="material not found")

    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    upsert_material({
        "material_id": material_id,
        "status": "transcoding",
        "updated_at": now,
    })

    # 用后台任务模拟异步完成，保证 uploaded -> transcoding -> ready
    # 这条链路在本地可验证。
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

    # 本地索引字段名和对外接口字段名并不完全一致，这里统一做一次映射。
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
