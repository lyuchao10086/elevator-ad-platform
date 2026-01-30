from fastapi import APIRouter
from app.schemas.device import DeviceRegisterRequest, DeviceRegisterResponse

import uuid
import redis # 1. 引入 Redis
from app.core.config import settings # 假设你配置都在这里

router = APIRouter()

# 连接 Redis (配置要和 Go 网关连接的 Redis 一致)
rdb = redis.Redis(
    host=settings.redis_host, 
    port=settings.redis_port, 
    db=0, 
    decode_responses=True
)

# PR-1：先内存存一下，后面再换 DB
_DEVICE_STORE = {}  # device_id -> token

# 连接 Redis (确保和 Go 用的是同一个 Redis)
rdb = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

@router.post("/register", response_model=DeviceRegisterResponse)
def register_device(payload: DeviceRegisterRequest):
    # 生成 ID 和 Token
    device_id = f"ELEVATOR_{uuid.uuid4().hex[:6].upper()}"
    token = f"sk_{uuid.uuid4().hex}"

    # --- 核心修改：写入 Redis ---
    # Key 格式必须对应 Go manager.go 里的 "auth:" + deviceID
    rdb.set(f"auth:{device_id}", token)
    
    # 可选：顺便存一下设备信息供 Python 业务查询
    # 存 token 用于鉴权
    rdb.set(f"auth:{device_id}", token)

    # 分开存设备信息
    rdb.hset(f"device:info:{device_id}", "location", payload.location)
    rdb.hset(f"device:info:{device_id}", "registered_at", str(uuid.uuid1()))
    
    # -------------------------

    return DeviceRegisterResponse(
        device_id=device_id,
        token=token,
        location=payload.location,
    )

# ... 你原有的代码 (rdb, register_device 等) ...

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