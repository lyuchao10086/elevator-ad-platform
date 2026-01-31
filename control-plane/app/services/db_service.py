import os
import logging
import psycopg2
from psycopg2.extras import RealDictCursor


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
            print(sql, params) # sql输出调试
            cur.execute(sql, params)
            rows = cur.fetchall()
            print(f"Fetched {len(rows)} rows") # 调试输出行数
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
