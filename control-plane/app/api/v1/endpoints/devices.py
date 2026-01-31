from fastapi import APIRouter, HTTPException
from app.schemas.device import DeviceRegisterRequest, DeviceRegisterResponse
import uuid
from app.services import db_service

router = APIRouter()


# PR-1：注册接口仍使用内存暂存
_DEVICE_STORE = {}  # device_id -> token


@router.post("/register", response_model=DeviceRegisterResponse)
def register_device(payload: DeviceRegisterRequest):
    device_id = f"dev_{uuid.uuid4().hex[:8]}"
    token = f"devtok_{uuid.uuid4().hex}"

    _DEVICE_STORE[device_id] = token

    return DeviceRegisterResponse(
        device_id=device_id,
        token=token,
        location=payload.location,
    )


@router.get("/", summary="List devices")
def list_devices(q: str = None, page: int = 1, page_size: int = 20):
    print("q是",q) #debug
    try:
        # normalize pagination
        if page < 1:
            page = 1
        if page_size < 1 or page_size > 1000:
            page_size = 20
        offset = (page - 1) * page_size
        items = db_service.list_devices(limit=page_size, offset=offset, q=q)
        total = db_service.count_devices(q=q)
        return {"total": total, "items": items}
    except Exception as e:
        # return an empty list with error message to aid frontend debugging
        return {"total": 0, "items": [], "error": str(e)}
