from fastapi import APIRouter
from app.api.v1.endpoints import devices, devices_snapshot, campaigns, materials, debug,commands  # 以及 campaigns/materials/...
from app.services import db_service

import redis  # 引入 redis 库
from app.core.config import settings # 引入配置

# 在这里定义 rdb 对象，这样下面的 get_summary 才能找到它
rdb = redis.Redis(
    host=settings.redis_host, 
    port=settings.redis_port, 
    db=0, 
    decode_responses=True
)

api_router = APIRouter()

# 1. 挂载标准的 v1 路由
api_router.include_router(devices.router, prefix="/devices", tags=["Devices"])
api_router.include_router(devices_snapshot.router, prefix="/devices/remote", tags=["Remote Ctrl"])
api_router.include_router(materials.router, prefix="/materials", tags=["Materials"])
api_router.include_router(campaigns.router, prefix="/campaigns", tags=["Campaigns"])
api_router.include_router(debug.router, prefix="/debug", tags=["Debug"])
api_router.include_router(commands.router, prefix="/commands", tags=["Commands"]) 

# 2. analytics summary: 从数据库读取在线/离线设备数量；播放相关指标暂用 0
@api_router.get("/analytics/summary")
def get_summary():
    try:
        # 1. 获取数据库里的设备总数
        # 既然原来的代码用了 count_devices_status()，我们可以求和得到总数
        counts = db_service.count_devices_status()
        total_devices = sum(counts.values()) 

        # 2. 从 Redis 实时统计在线数量
        # keys() 会返回所有匹配 device:online:* 的 key 列表
        online_keys = rdb.keys("device:online:*")
        online_count = len(online_keys)

        # 3. 计算离线数量
        offline_count = max(0, total_devices - online_count)

        return {
            "online": online_count, 
            "offline": offline_count, 
            "plays": 0, 
            "complete_rate": 0
        }
    except Exception as e:
        # 打印错误日志，方便调试
        print(f"统计报错: {e}")
        return {"online": 0, "offline": 0, "plays": 0, "complete_rate": 0}
# 如果前端没带 v1 访问 /api/devices，我们也接住它
@api_router.get("/devices")
def get_devices_no_v1():
    # 这里直接重用 devices.list_devices
    return devices.list_devices()