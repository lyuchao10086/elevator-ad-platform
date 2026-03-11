from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from app.services import db_service

router = APIRouter()


@router.get("/", response_model=dict)
def list_ad_logs(offset: int = 0, limit: int = 50, device_id: str = None, ad_file_name: str = None, q: str = None):
    try:
        items = db_service.list_ad_logs(limit=limit, offset=offset, device_id=device_id, ad_file_name=ad_file_name, q=q)
        total = db_service.count_ad_logs(device_id=device_id, ad_file_name=ad_file_name, q=q)
        return {"total": total, "items": items}
    except Exception as e:
        import logging
        logging.exception('failed to list ad_logs')
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{log_id}")
def get_one_log(log_id: str):
    try:
        row = db_service.get_ad_log(log_id)
        if not row:
            raise HTTPException(status_code=404, detail="log not found")
        return row
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.exception('failed to get ad_log')
        raise HTTPException(status_code=500, detail=str(e))
