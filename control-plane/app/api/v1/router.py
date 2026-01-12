from fastapi import APIRouter
from app.api.v1.endpoints import devices, materials, campaigns

api_router = APIRouter()

api_router.include_router(devices.router, prefix="/devices", tags=["Devices"])
api_router.include_router(materials.router, prefix="/materials", tags=["Materials"])
api_router.include_router(campaigns.router, prefix="/campaigns", tags=["Campaigns"])
