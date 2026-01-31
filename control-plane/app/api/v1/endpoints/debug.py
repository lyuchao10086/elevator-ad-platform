from fastapi import APIRouter, HTTPException
from app.services import db_service

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
