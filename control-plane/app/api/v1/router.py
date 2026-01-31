from fastapi import APIRouter
from app.api.v1.endpoints import devices, devices_snapshot,campaigns,materials,debug  # 以及 campaigns/materials/...

api_router = APIRouter()

api_router.include_router(devices.router, prefix="/devices", tags=["Devices"])
api_router.include_router(devices_snapshot.router, prefix="/devices/remote", tags=["Remote Ctrl"])

api_router.include_router(materials.router, prefix="/materials", tags=["Materials"])
api_router.include_router(campaigns.router, prefix="/campaigns", tags=["Campaigns"])
api_router.include_router(debug.router, prefix="/debug", tags=["Debug"])
#api_router.include_router(schedules.router, prefix="/schedules", tags=["Schedules"])
