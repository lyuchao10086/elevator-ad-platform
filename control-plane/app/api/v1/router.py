from fastapi import APIRouter
from app.api.v1.endpoints import devices, remote_ctrl  # 以及 campaigns/materials/...

api_router = APIRouter()
api_router.include_router(devices.router, prefix="/devices", tags=["Devices"])
api_router.include_router(remote_ctrl.router, prefix="/devices/remote", tags=["Remote Ctrl"])
