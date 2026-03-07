from fastapi import APIRouter
from app.api.v1.endpoints import devices, devices_snapshot, campaigns, materials, debug,commands, ad_logs, ad_stats  # 以及 campaigns/materials/...
from app.services import db_service
import redis
from app.core.config import settings

api_router = APIRouter()

# 1. 挂载标准的 v1 路由
api_router.include_router(devices.router, prefix="/devices", tags=["Devices"])
api_router.include_router(devices_snapshot.router, prefix="/devices/remote", tags=["Remote Ctrl"])
api_router.include_router(materials.router, prefix="/materials", tags=["Materials"])
api_router.include_router(campaigns.router, prefix="/campaigns", tags=["Campaigns"])
api_router.include_router(debug.router, prefix="/debug", tags=["Debug"])

api_router.include_router(commands.router, prefix="/commands", tags=["Commands"]) 
api_router.include_router(ad_logs.router, prefix="/ad_logs", tags=["AdLogs"]) 
api_router.include_router(ad_stats.router, prefix="/ad_stats", tags=["AdStats"]) 

# 2. analytics summary: 从数据库读取在线/离线设备数量；播放相关指标暂用 0
@api_router.get("/analytics/summary")
def get_summary():
    try:
        # 优先使用 Redis 统计：与 Go 网关写入的 key 保持一致 (device:online:<device_id>)
        try:
            rdb = redis.Redis(
                host=getattr(settings, 'redis_host', '127.0.0.1'),
                port=getattr(settings, 'redis_port', 6379),
                db=getattr(settings, 'redis_db', 0),
                decode_responses=True,
            )
            # keys 可能在大规模环境下性能欠佳；此处为简单实现，若需优化可改为 scan/schildren/统计集合
            online_keys = rdb.keys("device:online:*") or []
            online = int(len(online_keys))
            # 尝试使用 registered_devices 集合作为设备总数的来源（register 接口会维护该集合）
            try:
                registered = int(rdb.scard('registered_devices') or 0)
                offline = max(0, registered - online)
            except Exception:
                # 若 Redis 中没有 registered_devices，则回退到 DB 的统计
                counts = db_service.count_devices_status()
                offline = counts.get('offline', 0) + counts.get('OFFLINE', 0)

            return {"online": int(online), "offline": int(offline), "plays": 0, "complete_rate": 0}
        except Exception:
            # Redis 不可用时回退到 DB 统计
            counts = db_service.count_devices_status()
            online = counts.get('online', 0) + counts.get('ONLINE', 0)
            offline = counts.get('offline', 0) + counts.get('OFFLINE', 0)
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