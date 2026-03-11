from fastapi import APIRouter, HTTPException
from app.services import db_service
from app.services.material_service import update_material_status

router = APIRouter()


@router.get("/db/ping")
def db_ping():
    try:
        conn = db_service.get_conn()
        cur = conn.cursor()
        cur.execute('SELECT 1')
        cur.fetchone()
        cur.execute('SELECT count(1) FROM devices')
        cnt = cur.fetchone()[0]
        conn.close()
        return {"ok": True, "devices_count": cnt}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/materials/{material_id}/status/{status}")
def _dbg_update_status(material_id: str, status: str):
    try:
        return update_material_status(material_id, status)
    except KeyError:
        raise HTTPException(status_code=404, detail="material not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get('/db/commands')
def db_commands(limit: int = 100, offset: int = 0):
    """调试接口：直接从数据库读取 `command_logs` 表并返回（用于排查前端未显示数据的问题）"""
    try:
        items = db_service.list_commands(limit=limit, offset=offset)
        return {"ok": True, "items": items, "total": len(items)}
    except Exception as e:
        # 返回详细错误以便调试（非生产用）
        raise HTTPException(status_code=500, detail=str(e))
