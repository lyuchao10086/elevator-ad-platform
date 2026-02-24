import os
import logging
import psycopg2
from psycopg2.extras import RealDictCursor, Json


def get_conn():
    # Try to load .env in control-plane directory if present (simple parser)
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        env_path = os.path.join(base_dir, '.env')
        if os.path.exists(env_path):
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#') or '=' not in line:
                        continue
                    k, v = line.split('=', 1)
                    k = k.strip(); v = v.strip().strip('"').strip("'")
                    if k not in os.environ:
                        os.environ[k] = v
    except Exception:
        logging.exception('failed to load .env')

    # DSN from env or build from parts
    dsn = os.getenv('PG_DSN')
    if not dsn:
        host = os.getenv('PG_HOST', 'localhost')
        port = os.getenv('PG_PORT', '5432')
        user = os.getenv('PG_USER', 'postgres')
        password = os.getenv('PG_PASSWORD', '538890')
        db = os.getenv('PG_DB', 'elevator_ad')
        dsn = f"host={host} port={port} user={user} password={password} dbname={db}"
    try:
        conn = psycopg2.connect(dsn)
        try:
            # ensure client uses UTF8; helps psycopg2 decode text columns correctly
            conn.set_client_encoding('UTF8')
        except Exception:
            pass
        return conn
    except Exception:
        logging.exception('failed to connect to Postgres with dsn: %s', dsn)
        raise


def list_devices(limit=100, offset=0, q=None):
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        # 使用 SELECT * 避免因数据库列不一致导致查询失败
        sql = "SELECT * FROM devices"
        params = []
        if q:
            sql += " WHERE device_id ILIKE %s OR name ILIKE %s"
            like = f"%{q}%"
            params.extend([like, like])
        sql += " ORDER BY device_id LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        try:
            cur.execute(sql, params)
            rows = cur.fetchall()
        except UnicodeDecodeError as ude:
            # Fallback: some DB text may be in a different encoding (e.g., latin1/gbk).
            logging.warning('UnicodeDecodeError during fetchall: %s. Retrying with latin1 fallback.', ude)
            try:
                conn.set_client_encoding('LATIN1')
            except Exception:
                pass
            cur.execute(sql, params)
            rows = cur.fetchall()
            # rows currently decoded as latin1; we'll re-decode text fields to UTF-8 where possible
            for r in rows:
                for k, v in list(r.items()):
                    if isinstance(v, str):
                        try:
                            b = v.encode('latin1')
                            # try decode as utf-8, fallback to replace
                            try:
                                r[k] = b.decode('utf-8')
                            except Exception:
                                r[k] = b.decode('utf-8', errors='replace')
                        except Exception:
                            # keep original if any error
                            pass
        # add a default status field for frontend compatibility
        # 柔性兼容：为前端期望的字段补默认值，避免前端空表或报错
        for r in rows:
            if 'device_id' not in r:
                # 如果没有主键字段，跳过该记录（极少见）
                continue
            r.setdefault('name', '')
            r.setdefault('lon', None)
            r.setdefault('lat', None)
            r.setdefault('city', '')
            r.setdefault('building', '')
            r.setdefault('firmware_version', '')
            # tags 在 DB 中可能为 text[] 或 json 字段，确保返回可序列化类型
            if 'tags' not in r or r.get('tags') is None:
                r['tags'] = []
            
            if 'status' not in r:
                r['status'] = 'unknown'
        return rows
    finally:
        conn.close()


def count_devices(q=None):
    conn = get_conn()
    try:
        cur = conn.cursor()
        sql = "SELECT COUNT(1) FROM devices"
        params = []
        if q:
            sql += " WHERE device_id ILIKE %s OR name ILIKE %s"
            like = f"%{q}%"
            params.extend([like, like])
        cur.execute(sql, params)
        return cur.fetchone()[0]
    finally:
        conn.close()


def count_devices_status():
    """
    返回按 status 分组的设备计数，返回 dict，例如: {'online': 10, 'offline': 5}
    """
    conn = get_conn()
    try:
        cur = conn.cursor()
        sql = "SELECT status, COUNT(1) FROM devices GROUP BY status"
        cur.execute(sql)
        rows = cur.fetchall()
        result = {}
        for status, cnt in rows:
            key = status if status is not None else 'unknown'
            result[key] = int(cnt)
        return result
    finally:
        conn.close()


def list_materials(limit=100, offset=0):
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        sql = "SELECT * FROM materials ORDER BY material_id LIMIT %s OFFSET %s"
        params = [limit, offset]
        cur.execute(sql, params)
        rows = cur.fetchall()
        return rows
    finally:
        conn.close()


def insert_material(meta: dict):
    """
    Insert or update a material record into Postgres materials table.
    Accepts a dict produced by upload endpoint (keys: material_id, ad_id, file_name, oss_url, md5,
    type, duration_sec, size_bytes, uploader_id, status, versions, tags, extra, created_at, updated_at)
    """
    conn = get_conn()
    try:
        cur = conn.cursor()
        # discover existing columns to build compatible insert
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'materials'")
        cols = {r[0] for r in cur.fetchall()}

        if 'material_id' not in cols:
            # cannot persist without PK
            raise RuntimeError('materials table does not have material_id column')

        # desired order of candidate columns
        candidates = [
            'material_id', 'advertiser', 'ad_id', 'file_name', 'oss_url', 'md5', 'type', 'duration_sec', 'size_bytes',
            'uploader_id', 'status', 'versions', 'tags', 'extra', 'created_at', 'updated_at'
        ]

        use_cols = [c for c in candidates if c in cols]
        # ensure updated_at present: if not provided, fall back to created_at
        if 'updated_at' in use_cols and meta.get('updated_at') is None and meta.get('created_at') is not None:
            meta['updated_at'] = meta.get('created_at')
        values = []
        for c in use_cols:
            v = meta.get(c)
            # fall back for file_name/filename
            if c == 'file_name' and v is None:
                v = meta.get('filename')
            if c in ('versions', 'tags', 'extra'):
                values.append(Json(v) if v is not None else None)
            else:
                values.append(v)

        placeholders = ','.join(['%s'] * len(use_cols))
        col_list = ','.join(use_cols)

        # build ON CONFLICT update clause for cols other than material_id
        update_cols = [c for c in use_cols if c != 'material_id']
        if update_cols:
            update_clause = ','.join([f"{c}=EXCLUDED.{c}" for c in update_cols])
            sql = f"INSERT INTO materials ({col_list}) VALUES ({placeholders}) ON CONFLICT (material_id) DO UPDATE SET {update_clause}"
        else:
            sql = f"INSERT INTO materials ({col_list}) VALUES ({placeholders}) ON CONFLICT (material_id) DO NOTHING"

        cur.execute(sql, values)
        conn.commit()
    finally:
        conn.close()


def get_material(material_id: str):
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        sql = "SELECT * FROM materials WHERE material_id = %s"
        cur.execute(sql, [material_id])
        row = cur.fetchone()
        return row
    finally:
        conn.close()


def list_campaigns(limit=100, offset=0):
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        sql = "SELECT * FROM campaigns ORDER BY campaign_id LIMIT %s OFFSET %s"
        params = [limit, offset]
        cur.execute(sql, params)
        rows = cur.fetchall()
        return rows
    finally:
        conn.close()


def get_campaign(campaign_id: str):
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        sql = "SELECT * FROM campaigns WHERE campaign_id = %s"
        cur.execute(sql, [campaign_id])
        row = cur.fetchone()
        return row
    finally:
        conn.close()


def update_campaign_status(campaign_id: str, status: str):
    conn = get_conn()
    try:
        cur = conn.cursor()
        sql = "UPDATE campaigns SET status = %s, updated_at = now() WHERE campaign_id = %s"
        cur.execute(sql, [status, campaign_id])
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()
