from fastapi import APIRouter
from app.schemas.device import DeviceRegisterRequest, DeviceRegisterResponse

import uuid

router = APIRouter()

# PR-1：先内存存一下，后面再换 DB
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
