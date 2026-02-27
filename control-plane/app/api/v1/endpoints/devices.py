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
    """
    返回设备列表：优先从数据库分页读取，再尝试合并 Redis 中在线状态。
    如果数据库为空或不可用，则尝试从 Redis 的 `auth:*` key 扫描生成临时列表。
    Redis 的错误会被吞掉（降级到纯 DB 响应），避免前端因为 Redis 可用但无数据而显示空列表。
    """
    try:
        if page < 1:
            page = 1
        if page_size < 1 or page_size > 1000:
            page_size = 20
        offset = (page - 1) * page_size

        items = db_service.list_devices(limit=page_size, offset=offset, q=q)
        total = db_service.count_devices(q=q)

        # 尝试合并 Redis 中的在线状态（best-effort）
        if rdb:
            try:
                for it in items:
                    did = it.get('device_id') or it.get('id')
                    if not did:
                        it['status'] = it.get('status', 'unknown')
                        continue
                    online_key = f"device:online:{did}"
                    try:
                        it['status'] = 'online' if rdb.exists(online_key) else it.get('status', 'offline')
                    except Exception:
                        it['status'] = it.get('status', 'offline')
            except Exception:
                # Redis 读取失败时忽略，返回 DB 数据
                pass

        # 如果 DB 没有任何设备，则尝试从 Redis 的 auth:* 生成临时列表（方便 dev mock）
        if (not items or len(items) == 0) and rdb:
            try:
                keys = rdb.keys('auth:*')
                items = []
                for k in keys:
                    d_id = k.split(':')[-1]
                    status = 'online' if rdb.exists(f'device:online:{d_id}') else 'offline'
                    items.append({
                        'device_id': d_id,
                        'name': f'电梯_{d_id[-4:]}',
                        'status': status,
                        'firmware_version': 'v1.0.0'
                    })
                total = len(items)
            except Exception:
                # 忽略 Redis 错误
                pass

        return {"total": total, "items": items}
    except Exception as e:
        return {"total": 0, "items": [], "error": str(e)}
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
