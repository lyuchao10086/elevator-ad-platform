from fastapi import APIRouter
from app.api.v1.endpoints import devices, devices_snapshot,campaigns,materials,debug,commands  # 以及 campaigns/materials/...

api_router = APIRouter()

# 1. 挂载标准的 v1 路由
api_router.include_router(devices.router, prefix="/devices", tags=["Devices"])
api_router.include_router(devices_snapshot.router, prefix="/devices/remote", tags=["Remote Ctrl"])
api_router.include_router(materials.router, prefix="/materials", tags=["Materials"])
api_router.include_router(campaigns.router, prefix="/campaigns", tags=["Campaigns"])
api_router.include_router(debug.router, prefix="/debug", tags=["Debug"])

api_router.include_router(commands.router, prefix="/commands", tags=["Commands"]) 

# 2. 【核心修复】给前端那些“自动请求”补上路标，消除终端 404
@api_router.get("/analytics/summary")
def get_mock_summary():
    return {"online": 1, "offline": 0, "plays": 88, "complete_rate": 99}

# 如果前端没带 v1 访问 /api/devices，我们也接住它
@api_router.get("/devices")
def get_devices_no_v1():
    # 这里直接重定向或复用上面的逻辑
    return devices.list_devices()