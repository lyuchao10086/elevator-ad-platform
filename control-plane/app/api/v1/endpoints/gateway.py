from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from app.api.v1.endpoints import campaigns as campaigns_ep
from app.services import db_service
from app.services.material_service import (
    get_material as get_local_material,
    get_material_file_path,
    list_materials as list_local_materials,
)

router = APIRouter()


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _pick_latest_published_campaign_from_memory(device_id: str) -> Optional[dict]:
    candidates = []
    for row in campaigns_ep._CAMPAIGN_STORE.values():
        if row.get("status") != "published":
            continue
        target_devices = campaigns_ep._normalize_target_devices(row.get("target_device_groups") or [])
        if device_id in target_devices:
            candidates.append(row)
    if not candidates:
        return None
    candidates.sort(
        key=lambda x: (
            str(x.get("updated_at") or ""),
            str(x.get("created_at") or ""),
            str(x.get("campaign_id") or ""),
        ),
        reverse=True,
    )
    return candidates[0]


def _get_published_campaign_for_device(device_id: str) -> dict:
    db_error = False
    try:
        campaign = db_service.get_latest_published_campaign_for_device(device_id)
    except Exception:
        campaign = None
        db_error = True

    if not campaign and campaigns_ep._fallback_enabled():
        campaign = _pick_latest_published_campaign_from_memory(device_id)

    if not campaign and db_error and not campaigns_ep._fallback_enabled():
        raise HTTPException(status_code=503, detail="database unavailable")
    if not campaign:
        raise HTTPException(status_code=404, detail="published schedule not found for device")
    return campaign


def _normalize_material_row(raw: Dict[str, Any]) -> Dict[str, Any]:
    extra = raw.get("extra") or {}
    return {
        "material_id": raw.get("material_id") or raw.get("id"),
        "ad_id": raw.get("ad_id"),
        "advertiser": raw.get("advertiser"),
        "file_name": raw.get("file_name") or raw.get("filename"),
        "oss_url": raw.get("oss_url") or extra.get("oss_url"),
        "md5": raw.get("md5"),
        "type": raw.get("type"),
        "duration_sec": raw.get("duration_sec") or extra.get("duration"),
        "size_bytes": raw.get("size_bytes") or raw.get("size") or 0,
        "uploader_id": raw.get("uploader_id"),
        "status": raw.get("status"),
        "versions": raw.get("versions"),
        "tags": raw.get("tags"),
        "created_at": raw.get("created_at"),
        "updated_at": raw.get("updated_at"),
        "extra": extra,
    }


def _list_material_rows_from_any_source() -> List[Dict[str, Any]]:
    try:
        rows = db_service.list_materials(limit=10000, offset=0)
        return [_normalize_material_row(r) for r in rows]
    except Exception:
        pass

    rows = list_local_materials(offset=0, limit=10000)
    return [_normalize_material_row(r) for r in rows]


def _pick_material_for_identifier(identifier: str) -> Optional[Dict[str, Any]]:
    if not isinstance(identifier, str) or not identifier.strip():
        return None
    key = identifier.strip()

    try:
        row = db_service.get_material(key)
    except Exception:
        row = None
    if row:
        return _normalize_material_row(row)

    local_row = get_local_material(key)
    if local_row:
        return _normalize_material_row(local_row)

    for row in _list_material_rows_from_any_source():
        if row.get("ad_id") == key or row.get("material_id") == key or row.get("file_name") == key:
            return row
    return None


def _pick_material_for_ad_id(ad_id: str) -> Optional[Dict[str, Any]]:
    return _pick_material_for_identifier(ad_id)


def _resolve_material_source_url(
    material_row: Optional[Dict[str, Any]],
    playlist_item: Dict[str, Any],
    schedule_json: Dict[str, Any],
) -> Optional[str]:
    if material_row and material_row.get("oss_url"):
        return material_row.get("oss_url")

    file_name = None
    if material_row:
        file_name = material_row.get("file_name")
    if not file_name:
        file_name = playlist_item.get("file")
    if not isinstance(file_name, str) or not file_name:
        return None

    base_url = schedule_json.get("download_base_url")
    if not isinstance(base_url, str) or not base_url.strip():
        return None
    return base_url.rstrip("/") + "/" + file_name.lstrip("/")


def _build_asset_item(
    request: Request,
    playlist_item: Dict[str, Any],
    material_row: Optional[Dict[str, Any]],
    schedule_json: Dict[str, Any],
) -> Dict[str, Any]:
    ad_id = str(playlist_item.get("id") or "")
    material_id = material_row.get("material_id") if material_row else None
    download_url = None
    metadata_url = None
    file_exists = False
    if material_id:
        download_url = str(
            request.url_for("gateway_download_material_file", material_id=material_id)
        )
        metadata_url = str(
            request.url_for("gateway_get_material_metadata", material_id=material_id)
        )
        file_exists = bool(get_material_file_path(material_id))

    extra = (material_row or {}).get("extra") or {}
    signed_source_url = extra.get("signed_oss_url") or extra.get("signed_url")

    return {
        "id": ad_id,
        "material_id": material_id,
        "type": material_row.get("type") if material_row else None,
        "filename": (material_row.get("file_name") if material_row else None) or playlist_item.get("file"),
        "md5": (material_row.get("md5") if material_row else None) or playlist_item.get("md5"),
        "duration": material_row.get("duration_sec") if material_row else None,
        "size_bytes": material_row.get("size_bytes") if material_row else 0,
        "priority": playlist_item.get("priority"),
        "slots": playlist_item.get("slots") or [],
        "status": material_row.get("status") if material_row else "missing",
        "available": material_id is not None,
        "file_exists": file_exists,
        "download_url": download_url,
        "metadata_url": metadata_url,
        "source_url": _resolve_material_source_url(material_row, playlist_item, schedule_json),
        "signed_source_url": signed_source_url,
    }


def _build_device_schedule_bundle(request: Request, device_id: str, campaign: Dict[str, Any]) -> Dict[str, Any]:
    schedule_json = campaigns_ep._normalize_schedule_json(campaign.get("schedule_json"))
    if not schedule_json:
        raise HTTPException(status_code=400, detail="invalid schedule_json")

    edge_schedule = campaigns_ep._build_edge_schedule(schedule_json)
    playlist = schedule_json.get("playlist") or []
    assets = []
    for item in playlist:
        if not isinstance(item, dict):
            continue
        ad_id = item.get("id")
        if not isinstance(ad_id, str) or not ad_id:
            continue
        material_row = _pick_material_for_ad_id(ad_id)
        assets.append(_build_asset_item(request, item, material_row, schedule_json))

    return {
        "device_id": device_id,
        "campaign_id": campaign.get("campaign_id"),
        "version": campaign.get("version") or schedule_json.get("version"),
        "generated_at": _utcnow_iso(),
        "schedule_format": "schedule-config",
        "schedule": schedule_json,
        "schedule_config": schedule_json,
        "edge_schedule": edge_schedule,
        "assets": assets,
    }


@router.get("/devices/{device_id}/schedule")
def get_device_schedule(
    device_id: str,
    format: Literal["schedule-config", "edge-schedule"] = "schedule-config",
):
    """
    Return the currently published schedule for one device.

    Default output is the README-style playlist JSON (`schedule-config`).
    `format=edge-schedule` is kept for compatibility with the existing
    terminal-side SyncSchedule shape.
    """
    campaign = _get_published_campaign_for_device(device_id)

    schedule_json = campaigns_ep._normalize_schedule_json(campaign.get("schedule_json"))
    if not schedule_json:
        raise HTTPException(status_code=400, detail="invalid schedule_json")

    if format == "edge-schedule":
        return campaigns_ep._build_edge_schedule(schedule_json)
    return schedule_json


@router.get("/devices/{device_id}/bundle")
def get_device_schedule_bundle(request: Request, device_id: str):
    """
    Return a device-level schedule bundle for gateway caching.

    The payload contains:
    - `schedule`: edge-consumable schedule JSON
    - `assets`: material metadata list used for prefetch/download
    """
    campaign = _get_published_campaign_for_device(device_id)
    return _build_device_schedule_bundle(request, device_id, campaign)


@router.get("/devices/{device_id}/materials")
def list_device_materials(request: Request, device_id: str):
    campaign = _get_published_campaign_for_device(device_id)
    bundle = _build_device_schedule_bundle(request, device_id, campaign)
    return {
        "device_id": device_id,
        "campaign_id": bundle.get("campaign_id"),
        "version": bundle.get("version"),
        "total": len(bundle.get("assets") or []),
        "items": bundle.get("assets") or [],
    }


@router.get("/materials/by-ad/{ad_id}")
def get_material_metadata_by_ad_id(request: Request, ad_id: str):
    row = _pick_material_for_ad_id(ad_id)
    if not row:
        raise HTTPException(status_code=404, detail="material not found for ad")

    material_id = row.get("material_id")
    return {
        **row,
        "download_url": str(
            request.url_for("gateway_download_material_file", material_id=material_id)
        ) if material_id else None,
        "metadata_url": str(
            request.url_for("gateway_get_material_metadata", material_id=material_id)
        ) if material_id else None,
    }


@router.get("/materials/{material_id}", name="gateway_get_material_metadata")
def get_material_metadata(request: Request, material_id: str):
    row = _pick_material_for_identifier(material_id)
    if not row:
        raise HTTPException(status_code=404, detail="material not found")

    resolved_id = row.get("material_id")
    p = get_material_file_path(resolved_id) if resolved_id else None
    return {
        **row,
        "file_exists": bool(p),
        "download_url": str(
            request.url_for("gateway_download_material_file", material_id=resolved_id)
        ) if resolved_id else None,
        "metadata_url": str(
            request.url_for("gateway_get_material_metadata", material_id=resolved_id)
        ) if resolved_id else None,
    }


@router.get("/materials/{material_id}/file", name="gateway_download_material_file")
def download_material_file(material_id: str):
    row = _pick_material_for_identifier(material_id)
    if not row or not row.get("material_id"):
        raise HTTPException(status_code=404, detail="material not found")

    p = get_material_file_path(row["material_id"])
    if not p:
        raise HTTPException(status_code=404, detail="material file not found")

    return FileResponse(
        path=str(p),
        filename=row.get("file_name") or p.name,
        media_type="application/octet-stream",
    )
