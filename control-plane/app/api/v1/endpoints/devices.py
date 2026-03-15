from fastapi import APIRouter, HTTPException
from app.schemas.device import DeviceRegisterRequest, DeviceRegisterResponse
import uuid
from app.services import db_service
import redis
from app.core.config import settings
import json

router = APIRouter()

_DEVICE_STORE = {}

# 连接 Redis (配置使用 settings)
# Redis 是 control-plane 和 Go 网关共享的运行时注册表：
# - auth:{device_id} 存设备鉴权 token
# - device:info:{device_id} 存轻量元数据
# - device:online:{device_id} 由网关维护在线心跳
rdb = redis.Redis(
    host=getattr(settings, 'redis_host', '10.12.58.42'), #服务器的ip地址
    port=getattr(settings, 'redis_port', 6379),
    db=getattr(settings, 'redis_db', 0),
    password='123456',
    decode_responses=True,
)

# 在 devices.py 中 rdb 初始化之后，list_devices 函数之前
print(f"DEBUG: 正在连接的 Redis 地址: {rdb.connection_pool.connection_kwargs.get('host')}")
print(f"DEBUG: 正在连接的 Redis 数据库编号 (DB): {rdb.connection_pool.connection_kwargs.get('db')}")

# 执行一次全库扫描，看看 Python 到底能看到什么 key
try:
    all_keys = rdb.keys("*")
    print(f"DEBUG: Python 在当前数据库中看到的全部 Key 数量: {len(all_keys)}")
    print(f"DEBUG: Python 看到的头 5 个 Key: {all_keys[:5]}")
except Exception as e:
    print(f"DEBUG: 扫描全库出错: {e}")

@router.post("/register", response_model=DeviceRegisterResponse)
def register_device(payload: DeviceRegisterRequest):
    # 生成 ID 和 Token（若前端未提供 device_id）
    device_id = payload.device_id or f"ELEVATOR_{uuid.uuid4().hex[:6].upper()}"
    token = f"sk_{uuid.uuid4().hex}"

    # 写入 Redis: 鉴权 token
    try:
        rdb.set(f"auth:{device_id}", token)
        # 存储设备信息到 Hash，便于快速查询
        info_key = f"device:info:{device_id}"
        info = {}
        for k in ('name','device_type','serial_no','tenant_id','city','building','floor','firmware_version','mac','last_seen_ip','group_id'):
            v = getattr(payload, k, None)
            if v is not None:
                info[k] = v
        # lon/lat 数值类型
        if payload.lon is not None: info['lon'] = str(payload.lon)
        if payload.lat is not None: info['lat'] = str(payload.lat)
        # tags：如果是可 JSON 化的，格式化为字符串存储
        if getattr(payload, 'tags', None) is not None:
            try:
                info['tags'] = json.dumps(payload.tags)
            except Exception:
                info['tags'] = str(payload.tags)

        if info:
            rdb.hset(info_key, mapping=info)
        rdb.hset(info_key, 'registered_at', str(uuid.uuid1()))
        # 额外维护一份设备集合，便于调试接口快速列出已注册设备，
        # 避免每次都全量扫描 Redis key。
        try:
            rdb.sadd('registered_devices', device_id)
        except Exception:
            pass
    except Exception:
        # Redis 不可用时不要中断注册流程
        pass

    # 写入数据库（Best-effort: upsert）
    try:
        meta = payload.dict(exclude_unset=True)
        meta['device_id'] = device_id
        if 'tags' in meta and isinstance(meta['tags'], str):
            meta['tags'] = [t.strip() for t in meta['tags'].split(',') if t.strip()] if meta['tags'] else None
        db_service.insert_device(**meta)
    except Exception:
        pass

    return DeviceRegisterResponse(
        device_id=device_id,
        token=token,
        name=getattr(payload, 'name', None),
        tenant_id=getattr(payload, 'tenant_id', None),
    )

@router.get("/", summary="List devices")
def list_devices(q: str = None, page: int = 1, page_size: int = 20):
    try:
        # 在接口层兜底分页参数，避免前端参数不完整时出现异常或超大查询。
        if page < 1:
            page = 1
        if page_size < 1 or page_size > 1000:
            page_size = 20
        offset = (page - 1) * page_size
        items = db_service.list_devices(limit=page_size, offset=offset, q=q)
        total = db_service.count_devices(q=q)
        # 2. 设备状态获取修改：当 Redis 连接正常，暂时用 Redis 状态覆盖 db中设备的假定状态
        if rdb:
            for it in items:
                d_id = it.get('device_id')
                if d_id:
                    # 检查 Redis 中是否存在该设备的心跳 Key
                    # 格式须和 Go 网关写入的一致，例如 device:online:ELEVATOR_123456
                    is_online = rdb.exists(f"device:online:{d_id}")
                    it['status'] = 'online' if is_online else 'offline'
        
        return {"total": total, "items": items}
    except Exception as e:
        # return an empty list with error message to aid frontend debugging
        return {"total": 0, "items": [], "error": str(e)}
# 如果需要一个只返回已在网关/Redis注册设备的接口，可以启用下面的路由并在前端调用 /devices/registered
@router.get("/registered", summary="List devices registered in Redis")
def list_registered_devices():
    try:
        # 这个接口主要用于联调排障：它展示的是 Redis 侧可被网关鉴权的设备，
        # 不是完整的 DB 管理视图。
        keys = rdb.keys("auth:*")
        items = []
        for k in keys:
            d_id = k.split(":")[-1]
            items.append({
                "device_id": d_id,
                "name": f"电梯_{d_id[-4:]}",
                "status": "online",
                "firmware_version": "v1.0.1",
            })
        return {"items": items, "total": len(items)}
    except Exception as e:
        return {"items": [], "total": 0, "error": str(e)}
