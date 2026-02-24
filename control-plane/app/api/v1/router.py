from fastapi import APIRouter
from app.api.v1.endpoints import devices, devices_snapshot, campaigns, materials, debug  # 以及 campaigns/materials/...
from app.services import db_service

api_router = APIRouter()

# 1. 挂载标准的 v1 路由
api_router.include_router(devices.router, prefix="/devices", tags=["Devices"])
api_router.include_router(devices_snapshot.router, prefix="/devices/remote", tags=["Remote Ctrl"])
api_router.include_router(materials.router, prefix="/materials", tags=["Materials"])
api_router.include_router(campaigns.router, prefix="/campaigns", tags=["Campaigns"])
api_router.include_router(debug.router, prefix="/debug", tags=["Debug"])

# 2. analytics summary: 从数据库读取在线/离线设备数量；播放相关指标暂用 0
@api_router.get("/analytics/summary")
def get_summary():
    try:
        counts = db_service.count_devices_status()
        online = counts.get('online', 0) + counts.get('ONLINE', 0)
        offline = counts.get('offline', 0) + counts.get('OFFLINE', 0)
        # 若 DB 中 status 字段值有其它命名（如 'unknown'），不计入 online/offline
        return {"online": int(online), "offline": int(offline), "plays": 0, "complete_rate": 0}
    except Exception as e:
        # 保持向前兼容：当查询失败时返回示例值并记录异常
        import logging
        logging.exception('failed to compute analytics summary')
        return {"online": 0, "offline": 0, "plays": 0, "complete_rate": 0}


# 如果前端没带 v1 访问 /api/devices，我们也接住它
@api_router.get("/devices")
def get_devices_no_v1():
    # 这里直接重用 devices.list_devices
    return devices.list_devices()