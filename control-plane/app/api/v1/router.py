from fastapi import APIRouter
import redis

from app.api.v1.endpoints import (
    ad_logs,
    ad_stats,
    campaigns,
    commands,
    debug,
    devices,
    devices_snapshot,
    gateway,
    materials,
)
from app.core.config import settings
from app.services import db_service

api_router = APIRouter()

# 1. standard v1 routes
api_router.include_router(devices.router, prefix="/devices", tags=["Devices"])
api_router.include_router(devices_snapshot.router, prefix="/devices/remote", tags=["Remote Ctrl"])
api_router.include_router(materials.router, prefix="/materials", tags=["Materials"])
api_router.include_router(campaigns.router, prefix="/campaigns", tags=["Campaigns"])
api_router.include_router(gateway.router, prefix="/gateway", tags=["Gateway"])
api_router.include_router(debug.router, prefix="/debug", tags=["Debug"])
api_router.include_router(commands.router, prefix="/commands", tags=["Commands"])
api_router.include_router(ad_logs.router, prefix="/ad_logs", tags=["AdLogs"])
api_router.include_router(ad_stats.router, prefix="/ad_stats", tags=["AdStats"])


@api_router.get("/analytics/summary")
def get_summary():
    try:
        try:
            rdb = redis.Redis(
                host=getattr(settings, "redis_host", "10.12.58.42"),
                port=getattr(settings, "redis_port", 6379),
                db=getattr(settings, "redis_db", 0),
                password="123456",
                decode_responses=True,
            )
            online_keys = rdb.keys("device:online:*") or []
            online = int(len(online_keys))
            try:
                total = db_service.count_devices()
                offline = max(0, total - online)
            except Exception:
                counts = db_service.count_devices_status()
                offline = counts.get("offline", 0) + counts.get("OFFLINE", 0)

            return {"online": int(online), "offline": int(offline), "plays": 0, "complete_rate": 0}
        except Exception:
            counts = db_service.count_devices_status()
            online = counts.get("online", 0) + counts.get("ONLINE", 0)
            offline = counts.get("offline", 0) + counts.get("OFFLINE", 0)
            return {"online": int(online), "offline": int(offline), "plays": 0, "complete_rate": 0}
    except Exception:
        import logging

        logging.exception("failed to compute analytics summary")
        return {"online": 0, "offline": 0, "plays": 0, "complete_rate": 0}


@api_router.get("/devices")
def get_devices_no_v1():
    return devices.list_devices()
