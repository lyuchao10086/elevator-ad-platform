from fastapi import APIRouter, HTTPException
from datetime import datetime
try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None
from app.services import db_service

router = APIRouter()


def _today_range_local(tz_name: str = 'Asia/Shanghai'):
    """Return (start, now) for today's range in given timezone (default Asia/Shanghai)."""
    if ZoneInfo is not None:
        tz = ZoneInfo(tz_name)
        now = datetime.now(tz)
    else:
        # fallback to naive local time if zoneinfo not available
        now = datetime.now()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, now


@router.get("/devices")
def devices_summary():
    """Return today's play stats aggregated by device."""
    start, now = _today_range_local()
    try:
        rows = db_service.list_ad_logs(limit=10000, offset=0, from_ts=start, to_ts=now)
        # 如果按今天过滤得到空结果，但表中有数据，则回退到不按时间过滤（提高容错性）
        if (not rows) and db_service.count_ad_logs() > 0:
            rows = db_service.list_ad_logs(limit=10000, offset=0)
        # aggregate by device_id
        groups = {}
        for r in rows:
            dev = r.get('device_id') or 'unknown'
            grp = groups.setdefault(dev, {'device_id': dev, 'plays': 0, 'sum_rate': 0.0, 'count_rate': 0, 'items': []})
            grp['plays'] += 1
            rate = r.get('completion_rate')
            # Exclude invalid logs (is_valid == False) from average calculation
            if rate is not None and r.get('is_valid') is not False:
                grp['sum_rate'] += float(rate)
                grp['count_rate'] += 1
            grp['items'].append({
                'log_id': r.get('log_id'),
                'ad_file_name': r.get('ad_file_name'),
                'duration_ms': r.get('duration_ms'),
                'completion_rate': r.get('completion_rate'),
                'play_result': r.get('play_result'),
                'billing_status': r.get('billing_status'),
                'audit_result': r.get('audit_result'),
            })

        results = []
        for dev, v in groups.items():
            avg = (v['sum_rate'] / v['count_rate']) if v['count_rate']>0 else None
            results.append({'device_id': dev, 'plays': v['plays'], 'avg_completion_rate': round(avg,4) if avg is not None else None})
        # sort by plays desc
        results.sort(key=lambda x: x['plays'], reverse=True)
        return {'total': len(results), 'items': results}
    except Exception as e:
        import logging
        logging.exception('failed to compute devices summary')
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/devices/{device_id}")
def device_detail(device_id: str):
    start, now = _today_range_local()
    try:
        rows = db_service.list_ad_logs(limit=10000, offset=0, device_id=device_id, from_ts=start, to_ts=now)
        if (not rows) and db_service.count_ad_logs() > 0:
            rows = db_service.list_ad_logs(limit=10000, offset=0, device_id=device_id)
        items = [
            {
                'log_id': r.get('log_id'),
                'ad_file_name': r.get('ad_file_name'),
                'start_time': r.get('start_time'),
                'end_time': r.get('end_time'),
                'duration_ms': r.get('duration_ms'),
                'is_valid': r.get('is_valid'),
                'billing_status': r.get('billing_status'),
                'audit_result': r.get('audit_result'),
                'completion_rate': r.get('completion_rate'),
                'play_result': r.get('play_result')
            }
            for r in rows
        ]
        return {'device_id': device_id, 'items': items}
    except Exception as e:
        import logging
        logging.exception('failed to get device detail')
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ads")
def ads_summary():
    """Return today's play stats aggregated by ad file name."""
    start, now = _today_range_local()
    try:
        rows = db_service.list_ad_logs(limit=100000, offset=0, from_ts=start, to_ts=now)
        if (not rows) and db_service.count_ad_logs() > 0:
            rows = db_service.list_ad_logs(limit=100000, offset=0)
        groups = {}
        for r in rows:
            ad = r.get('ad_file_name') or 'unknown'
            grp = groups.setdefault(ad, {
                'ad_file_name': ad,
                'plays': 0,
                'sum_rate': 0.0,
                'count_rate': 0,
                'items': [],
                'advertiser': None
            })
            # Count plays excluding logs explicitly marked invalid (is_valid == False)
            if r.get('is_valid') is not False:
                # prefer the first non-empty advertiser we see for this ad
                if not grp.get('advertiser'):
                    grp['advertiser'] = r.get('advertiser')
                grp['plays'] += 1
            rate = r.get('completion_rate')
            # Exclude logs with duration_ms == 0 (not started) and is_valid == False from average
            if rate is not None and (r.get('duration_ms') or 0) > 0 and r.get('is_valid') is not False:
                grp['sum_rate'] += float(rate)
                grp['count_rate'] += 1
            grp['items'].append({
                'advertiser': r.get('advertiser'),
                'log_id': r.get('log_id'),
                'device_id': r.get('device_id'),
                'duration_ms': r.get('duration_ms'),
                'completion_rate': r.get('completion_rate'),
                'play_result': r.get('play_result'),
                'billing_status': r.get('billing_status'),
                'audit_result': r.get('audit_result'),
            })

        results = []
        for ad, v in groups.items():
            avg = (v['sum_rate'] / v['count_rate']) if v['count_rate'] > 0 else None
            results.append({
                'ad_file_name': ad,
                'plays': v['plays'],
                'avg_completion_rate': round(avg,4) if avg is not None else None,
                'advertiser': v.get('advertiser')
            })
        results.sort(key=lambda x: x['plays'], reverse=True)
        return {'total': len(results), 'items': results}
    except Exception as e:
        import logging
        logging.exception('failed to compute ads summary')
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ads/{ad_file_name}")
def ad_detail(ad_file_name: str):
    start, now = _today_range_local()
    try:
        rows = db_service.list_ad_logs(limit=100000, offset=0, ad_file_name=ad_file_name, from_ts=start, to_ts=now)
        if (not rows) and db_service.count_ad_logs() > 0:
            rows = db_service.list_ad_logs(limit=100000, offset=0, ad_file_name=ad_file_name)
        items = [
            {
                'log_id': r.get('log_id'),
                'device_id': r.get('device_id'),
                'start_time': r.get('start_time'),
                'end_time': r.get('end_time'),
                'duration_ms': r.get('duration_ms'),
                'is_valid': r.get('is_valid'),
                'billing_status': r.get('billing_status'),
                'audit_result': r.get('audit_result'),
                'completion_rate': r.get('completion_rate'),
                'play_result': r.get('play_result')
            }
            for r in rows
        ]
        return {'ad_file_name': ad_file_name, 'items': items}
    except Exception as e:
        import logging
        logging.exception('failed to get ad detail')
        raise HTTPException(status_code=500, detail=str(e))


@router.get('/debug/count')
def debug_count():
    """Return total ad_logs count (no time filter) for quick diagnostics."""
    try:
        total = db_service.count_ad_logs()
        return { 'total_ad_logs': total }
    except Exception as e:
        import logging
        logging.exception('failed to get ad_logs count')
        raise HTTPException(status_code=500, detail=str(e))
