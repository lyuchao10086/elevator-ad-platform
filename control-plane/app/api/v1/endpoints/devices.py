from fastapi import APIRouter, HTTPException
from app.schemas.device import DeviceRegisterRequest, DeviceRegisterResponse
import uuid
from app.services import db_service
import redis
from app.core.config import settings

router = APIRouter()

# 初始化 Redis 客户端（配置来自 settings，兼容本地开发默认）
try:
    rdb = redis.Redis(host=getattr(settings, 'redis_host', 'localhost'), port=getattr(settings, 'redis_port', 6379), db=0, decode_responses=True)
except Exception:
    rdb = None


# 内存保留的兼容注册（仍写入 Redis 作为主要来源）
_DEVICE_STORE = {}


@router.post("/register", response_model=DeviceRegisterResponse)
def register_device(payload: DeviceRegisterRequest):
    device_id = f"ELEVATOR_{uuid.uuid4().hex[:6].upper()}"
    token = f"sk_{uuid.uuid4().hex}"

    # 写入 Redis（best-effort）
    try:
        if rdb:
            rdb.set(f"auth:{device_id}", token)
            rdb.hset(f"device:info:{device_id}", "location", payload.location)
            rdb.hset(f"device:info:{device_id}", "registered_at", str(uuid.uuid1()))
    except Exception:
        # 忽略 Redis 错误，保持向后兼容
        pass

    # 同步写入 DB（可选）
    try:
        db_service.insert_device(device_id=device_id, location=payload.location, status="online")
    except Exception:
        pass

    return DeviceRegisterResponse(device_id=device_id, token=token, location=payload.location)


@router.get("/", summary="List devices")
def list_devices(q: str = None, page: int = 1, page_size: int = 20):
    try:
        offset = (page - 1) * page_size
        # 1. 先从数据库拿到基础列表
        total = db_service.count_devices(q=q)
        items = db_service.list_devices(limit=page_size, offset=offset, q=q)

        # 2. 核心修改：只要 Redis 连接正常，就强制用 Redis 状态覆盖 SQL 状态
        if rdb:
            for it in items:
                d_id = it.get('device_id')
                if d_id:
                    # 检查 Redis 中是否存在该设备的心跳 Key
                    # 格式必须和你 Go 网关写入的一致，例如 device:online:ELEVATOR_123456
                    is_online = rdb.exists(f"device:online:{d_id}")
                    it['status'] = 'online' if is_online else 'offline'
        
        # 3. (可选) 如果你想让 Redis 里那台不在 SQL 里的 ELEV_001 也显示出来
        # 可以在这里做逻辑合并，但通常建议以数据库为准，Redis 只提供“在线”状态
        
        return {"total": total, "items": items}
    except Exception as e:
        return {"total": 0, "items": [], "error": str(e)}

# --- 在文件末尾添加这个函数 ---
@router.get("") # 这样就对应了 /api/v1/devices
def get_device_list():
    """
    不再写死 ID。
    当 mock_device.py 运行并注册后，Redis 里会有 auth:ELEVATOR_XXXX。
    我们动态把它们查出来。
    """
    keys = rdb.keys("auth:*")
    items = []
    for k in keys:
        d_id = k.split(":")[-1]
        items.append({
            "device_id": d_id,
            "name": f"电梯_{d_id[-4:]}",
            "status": "online",
            "firmware_version": "v1.0.1"
        })
    # return {"items": items, "total": len(items)}
    return {
            "items": items, 
            "total": len(items)
        }
