import os
import logging
import psycopg2
from psycopg2.extras import RealDictCursor, Json


def get_conn():
    # 统一在这里解析 .env 并建立数据库连接，避免各模块各自维护
    # Postgres 连接参数，降低本地开发和联调时的环境成本。
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
    # devices 表承担设备管理主视图的持久化查询职责；这里尽量补齐
    # 默认字段，减轻接口层和前端的兼容负担。
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
    # 与 list_devices 配套的分页总数查询，过滤条件保持一致。
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
    # materials 表是素材管理的持久化查询面；接口层会再映射成统一
    # 的 MaterialMeta 响应结构。
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
    将素材元数据写入 Postgres materials 表。

    这里采用“按现有列做兼容插入 + upsert”的策略，原因是联调阶段表结构
    可能还在演进，接口层不应该因为某个非核心字段缺失就整体失败。
    """
    conn = get_conn()
    try:
        cur = conn.cursor()
        # 动态探测表列，尽量兼容当前数据库里已有的表结构。
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'materials'")
        cols = {r[0] for r in cur.fetchall()}

        if 'material_id' not in cols:
            # cannot persist without PK
            raise RuntimeError('materials table does not have material_id column')

        # 约定稳定的字段顺序，便于构造 INSERT / UPSERT 语句。
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

        # material_id 是素材主键；重复上传同一素材时走 upsert，避免重复行。
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
    # 素材详情读取。上层会决定优先采用 DB 结果还是本地索引兜底。
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        sql = "SELECT * FROM materials WHERE material_id = %s"
        cur.execute(sql, [material_id])
        row = cur.fetchone()
        return row
    finally:
        conn.close()


def list_commands(limit=100, offset=0, q=None, device_id=None, action=None, from_ts=None, to_ts=None):
    """
    从数据库读取 `command_logs` 表，返回记录列表。
    支持按 `device_id` 或通用查询字符串 `q` 过滤（匹配 cmd_id / device_id / action）。
    将可能为毫秒的 `send_ts` 转换为秒以兼容前端。
    返回: list[dict]
    """
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        sql = "SELECT * FROM command_logs"
        params = []
        where = []
        if device_id:
            where.append("device_id = %s")
            params.append(device_id)
        if action:
            where.append("action = %s")
            params.append(action)
        # time range: accept from_ts/to_ts in seconds; DB may store seconds or milliseconds
        if from_ts is not None and to_ts is not None:
            # compare both seconds and milliseconds ranges to be robust
            where.append("((send_ts BETWEEN %s AND %s) OR (send_ts BETWEEN %s AND %s))")
            params.extend([from_ts, to_ts, int(from_ts*1000), int(to_ts*1000)])
        elif from_ts is not None:
            where.append("(send_ts >= %s OR send_ts >= %s)")
            params.extend([from_ts, int(from_ts*1000)])
        elif to_ts is not None:
            where.append("(send_ts <= %s OR send_ts <= %s)")
            params.extend([to_ts, int(to_ts*1000)])
        if q:
            where.append("(cmd_id ILIKE %s OR device_id ILIKE %s OR action ILIKE %s)")
            like = f"%{q}%"
            params.extend([like, like, like])
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY send_ts DESC NULLS LAST, created_at DESC NULLS LAST LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        try:
            cur.execute(sql, params)
            rows = cur.fetchall()
        except UnicodeDecodeError:
            # fallback to latin1 decoding
            try:
                conn.set_client_encoding('LATIN1')
            except Exception:
                pass
            cur.execute(sql, params)
            rows = cur.fetchall()

        # Normalize rows for frontend
        for r in rows:
            if 'cmd_id' not in r and 'id' in r:
                r['cmd_id'] = r.get('id')
            # ensure params/result present
            r['params'] = r.get('params') or r.get('params_json') or {}
            r['result'] = r.get('result') or r.get('data') or r.get('response') or {}
            # convert send_ts from ms to s if needed
            st = r.get('send_ts')
            try:
                if st is None:
                    r['send_ts'] = None
                else:
                    if isinstance(st, (int, float)) and st > 1e12:
                        r['send_ts'] = int(st // 1000)
                    else:
                        r['send_ts'] = int(st)
            except Exception:
                r['send_ts'] = r.get('send_ts')

        return rows
    finally:
        conn.close()


def count_commands(q=None, device_id=None, action=None, from_ts=None, to_ts=None):
    """Return total count of records in command_logs matching optional filters."""
    conn = get_conn()
    try:
        cur = conn.cursor()
        sql = "SELECT COUNT(1) FROM command_logs"
        params = []
        where = []
        if device_id:
            where.append("device_id = %s")
            params.append(device_id)
        if action:
            where.append("action = %s")
            params.append(action)
        if from_ts is not None and to_ts is not None:
            where.append("((send_ts BETWEEN %s AND %s) OR (send_ts BETWEEN %s AND %s))")
            params.extend([from_ts, to_ts, int(from_ts*1000), int(to_ts*1000)])
        elif from_ts is not None:
            where.append("(send_ts >= %s OR send_ts >= %s)")
            params.extend([from_ts, int(from_ts*1000)])
        elif to_ts is not None:
            where.append("(send_ts <= %s OR send_ts <= %s)")
            params.extend([to_ts, int(to_ts*1000)])
        if q:
            where.append("(cmd_id ILIKE %s OR device_id ILIKE %s OR action ILIKE %s)")
            like = f"%{q}%"
            params.extend([like, like, like])
        if where:
            sql += " WHERE " + " AND ".join(where)
        cur.execute(sql, params)
        return int(cur.fetchone()[0])
    finally:
        conn.close()


def list_ad_logs(limit=100, offset=0, device_id=None, ad_file_name=None, from_ts=None, to_ts=None, q=None):
    """
    列出 ad_logs 表内容，支持按 device_id、ad_file_name、时间范围和通用查询过滤。
    返回 list[dict]
    """
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        # 左连接 materials 表以获取素材记录中的 duration_sec（单位：秒）
        sql = "SELECT ad_logs.*, m.duration_sec AS material_duration_sec, m.advertiser AS advertiser FROM ad_logs LEFT JOIN materials m ON m.file_name = ad_logs.ad_file_name"
        params = []
        where = []
        if device_id:
            where.append("device_id = %s")
            params.append(device_id)
        if ad_file_name:
            where.append("ad_file_name ILIKE %s")
            params.append(f"%{ad_file_name}%")
        if from_ts is not None and to_ts is not None:
            where.append("(start_time BETWEEN %s AND %s)")
            params.extend([from_ts, to_ts])
        elif from_ts is not None:
            where.append("(start_time >= %s)")
            params.append(from_ts)
        elif to_ts is not None:
            where.append("(start_time <= %s)")
            params.append(to_ts)
        if q:
            where.append("(log_id ILIKE %s OR device_id ILIKE %s OR ad_file_name ILIKE %s)")
            like = f"%{q}%"
            params.extend([like, like, like])
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY start_time DESC NULLS LAST, created_at DESC NULLS LAST LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        try:
            cur.execute(sql, params)
            rows = cur.fetchall()
        except UnicodeDecodeError:
            try:
                conn.set_client_encoding('LATIN1')
            except Exception:
                pass
            cur.execute(sql, params)
            rows = cur.fetchall()

        # 对前端补齐稳定字段，并把原始日志转换成更适合展示/统计的结果。
        for r in rows:
            r.setdefault('log_id', r.get('log_id') or r.get('id'))
            r.setdefault('device_id', r.get('device_id'))
            r.setdefault('ad_file_name', r.get('ad_file_name'))
            r.setdefault('start_time', r.get('start_time'))
            r.setdefault('end_time', r.get('end_time'))
            r.setdefault('duration_ms', r.get('duration_ms'))
            r.setdefault('status_code', r.get('status_code'))
            r.setdefault('expected_md5', r.get('expected_md5'))
            r.setdefault('actual_md5', r.get('actual_md5'))
            r.setdefault('is_valid', r.get('is_valid'))
            r.setdefault('advertiser', r.get('advertiser') or '')
            r.setdefault('billing_status', r.get('billing_status'))
            r.setdefault('created_at', r.get('created_at'))

            # 完播率和播放结果属于业务层字段，不直接来自 ad_logs 原始列。
            try:
                # If is_valid explicitly false, treat as not played
                if r.get('is_valid') is False:
                    r['completion_rate'] = 0.0
                    r['play_result'] = '未播放'
                else:
                    dur_ms = r.get('duration_ms')
                    mat_sec = r.get('material_duration_sec')
                    if dur_ms is None or mat_sec is None or mat_sec == 0:
                        r['completion_rate'] = None
                        r['play_result'] = 'unknown'
                    else:
                        denom = float(mat_sec) * 1000.0
                        if denom <= 0:
                            r['completion_rate'] = None
                            r['play_result'] = 'unknown'
                        else:
                            rate = float(dur_ms) / denom
                            # clamp to sensible range
                            if rate < 0:
                                rate = 0.0
                            if rate > 10:
                                rate = 10.0
                            r['completion_rate'] = round(rate, 4)
                            # 判定：>95% 完播，<10% 未播放，其余 未完播
                            if rate > 0.95:
                                r['play_result'] = '完播'
                            elif rate < 0.10:
                                r['play_result'] = '未播放'
                            else:
                                r['play_result'] = '未完播'
            except Exception:
                r['completion_rate'] = None
                r['play_result'] = 'unknown'

        return rows
    finally:
        conn.close()


def count_ad_logs(device_id=None, ad_file_name=None, from_ts=None, to_ts=None, q=None):
    # ad_logs 列表页 / 统计页对应的总数查询。
    conn = get_conn()
    try:
        cur = conn.cursor()
        sql = "SELECT COUNT(1) FROM ad_logs"
        params = []
        where = []
        if device_id:
            where.append("device_id = %s")
            params.append(device_id)
        if ad_file_name:
            where.append("ad_file_name ILIKE %s")
            params.append(f"%{ad_file_name}%")
        if from_ts is not None and to_ts is not None:
            where.append("(start_time BETWEEN %s AND %s)")
            params.extend([from_ts, to_ts])
        elif from_ts is not None:
            where.append("(start_time >= %s)")
            params.append(from_ts)
        elif to_ts is not None:
            where.append("(start_time <= %s)")
            params.append(to_ts)
        if q:
            where.append("(log_id ILIKE %s OR device_id ILIKE %s OR ad_file_name ILIKE %s)")
            like = f"%{q}%"
            params.extend([like, like, like])
        if where:
            sql += " WHERE " + " AND ".join(where)
        cur.execute(sql, params)
        return int(cur.fetchone()[0])
    finally:
        conn.close()


def get_ad_log(log_id: str):
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        # 左连接 materials 以获取素材 duration_sec
        sql = "SELECT ad_logs.*, m.duration_sec AS material_duration_sec FROM ad_logs LEFT JOIN materials m ON m.file_name = ad_logs.ad_file_name WHERE ad_logs.log_id = %s"
        cur.execute(sql, [log_id])
        row = cur.fetchone()
        if not row:
            return None

        # compute completion_rate and play_result (reuse logic from list_ad_logs)
        try:
            if row.get('is_valid') is False:
                row['completion_rate'] = 0.0
                row['play_result'] = '未播放'
            else:
                dur_ms = row.get('duration_ms')
                mat_sec = row.get('material_duration_sec')
                if dur_ms is None or mat_sec is None or mat_sec == 0:
                    row['completion_rate'] = None
                    row['play_result'] = 'unknown'
                else:
                    denom = float(mat_sec) * 1000.0
                    if denom <= 0:
                        row['completion_rate'] = None
                        row['play_result'] = 'unknown'
                    else:
                        rate = float(dur_ms) / denom
                        if rate < 0:
                            rate = 0.0
                        if rate > 10:
                            rate = 10.0
                        row['completion_rate'] = round(rate, 4)
                        if rate > 0.95:
                            row['play_result'] = '完播'
                        elif rate < 0.10:
                            row['play_result'] = '未播放'
                        else:
                            row['play_result'] = '未完播'
        except Exception:
            row['completion_rate'] = None
            row['play_result'] = 'unknown'

        return row
    finally:
        conn.close()


def list_campaigns(limit=100, offset=0):
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        ensure_campaign_tables(cur)
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
        ensure_campaign_tables(cur)
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
        ensure_campaign_tables(cur)
        sql = "UPDATE campaigns SET status = %s, updated_at = now() WHERE campaign_id = %s"
        cur.execute(sql, [status, campaign_id])
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()

def insert_campaign(meta: dict):
    """
    Insert or update a campaign record into Postgres campaigns table.
    Compatible with partial schemas by introspecting existing columns.
    """
    conn = get_conn()
    try:
        cur = conn.cursor()
        ensure_campaign_tables(cur)
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'campaigns'")
        cols = {r[0] for r in cur.fetchall()}

        if 'campaign_id' not in cols:
            raise RuntimeError('campaigns table does not have campaign_id column')

        candidates = [
            'campaign_id', 'name', 'creator_id', 'status', 'schedule_json',
            'target_device_groups', 'start_at', 'end_at', 'version',
            'created_at', 'updated_at'
        ]
        use_cols = [c for c in candidates if c in cols]
        if 'updated_at' in use_cols and meta.get('updated_at') is None and meta.get('created_at') is not None:
            meta['updated_at'] = meta.get('created_at')

        values = []
        for c in use_cols:
            v = meta.get(c)
            if c in ('schedule_json', 'target_device_groups'):
                values.append(Json(v) if v is not None else None)
            else:
                values.append(v)

        placeholders = ','.join(['%s'] * len(use_cols))
        col_list = ','.join(use_cols)
        update_cols = [c for c in use_cols if c != 'campaign_id']
        if update_cols:
            update_clause = ','.join([f"{c}=EXCLUDED.{c}" for c in update_cols])
            sql = f"INSERT INTO campaigns ({col_list}) VALUES ({placeholders}) ON CONFLICT (campaign_id) DO UPDATE SET {update_clause}"
        else:
            sql = f"INSERT INTO campaigns ({col_list}) VALUES ({placeholders}) ON CONFLICT (campaign_id) DO NOTHING"

        cur.execute(sql, values)
        conn.commit()
    finally:
        conn.close()


def insert_device(**meta):
    """
    将设备元数据写入 devices 表。

    devices 表承载的是管理侧设备档案，和 Redis 中的运行时在线状态
    不是一回事；这里关注的是持久化元数据。
    """
    if 'device_id' not in meta:
        raise RuntimeError('device_id is required to insert_device')

    conn = get_conn()
    try:
        cur = conn.cursor()
        # 动态探测列结构，尽量兼容当前数据库中的 devices 表定义。
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'devices'")
        cols = {r[0] for r in cur.fetchall()}

        use_cols = [k for k in meta.keys() if k in cols]
        if not use_cols:
            # nothing to insert
            return

        values = []
        for c in use_cols:
            v = meta.get(c)
            # convert tags to Json where appropriate
            if c == 'tags':
                try:
                    from psycopg2.extras import Json as PgJson
                    values.append(PgJson(v) if v is not None else None)
                except Exception:
                    values.append(v)
            else:
                values.append(v)

        col_list = ','.join(use_cols)
        placeholders = ','.join(['%s'] * len(use_cols))

        # device_id 是管理侧主键；重复注册时更新已有设备元数据。
        update_cols = [c for c in use_cols if c != 'device_id']
        if update_cols:
            update_clause = ','.join([f"{c}=EXCLUDED.{c}" for c in update_cols])
            sql = f"INSERT INTO devices ({col_list}) VALUES ({placeholders}) ON CONFLICT (device_id) DO UPDATE SET {update_clause}, updated_at = NOW()"
        else:
            sql = f"INSERT INTO devices ({col_list}) VALUES ({placeholders}) ON CONFLICT (device_id) DO NOTHING"

        cur.execute(sql, values)
        conn.commit()
    finally:
        conn.close()


def insert_command(meta: dict):
    """
    将命令执行过程写入 command_logs。

    command_logs 是设备控制链路的审计表：谁给哪台设备发了什么命令、
    何时发、当前状态如何、回调结果是什么，都在这里追踪。
    """
    conn = get_conn()
    try:
        cur = conn.cursor()
        # 同样按实际表结构探测列，避免联调阶段因为列演进导致命令链路不可用。
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'command_logs'")
        cols = {r[0] for r in cur.fetchall()}

        if not cols:
            raise RuntimeError('command_logs table not found or has no columns')

        # 只插当前表真实存在的列，避免把扩展字段直接写崩。
        use_cols = [k for k in meta.keys() if k in cols]

        # If created_at column exists but not provided, set it to NOW()
        include_created_now = False
        if 'created_at' in cols and 'created_at' not in use_cols:
            include_created_now = True

        if not use_cols and not include_created_now:
            raise RuntimeError('no compatible columns to insert into command_logs')

        values = []
        for c in use_cols:
            v = meta.get(c)
            if c in ('params', 'result'):
                values.append(Json(v) if v is not None else None)
            else:
                values.append(v)

        # build SQL
        col_list = ','.join(use_cols + (['created_at'] if include_created_now else []))
        placeholders = ','.join(['%s'] * len(values) + (['NOW()'] if include_created_now else []))

        try:
            # 优先尝试直接插入；如果库表支持 id，则顺带返回记录标识。
            if 'id' in cols:
                sql = f"INSERT INTO command_logs ({col_list}) VALUES ({placeholders}) RETURNING id"
                cur.execute(sql, values)
                returned = cur.fetchone()
                conn.commit()
                return returned[0] if returned else None
            else:
                sql = f"INSERT INTO command_logs ({col_list}) VALUES ({placeholders})"
                cur.execute(sql, values)
                conn.commit()
                return None
        except Exception:
            # 如果插入失败且 cmd_id 已存在，则退化为按 cmd_id 更新，
            # 保证“先写 pending，后写 success/fail”的链路保持幂等。
            conn.rollback()
            if 'cmd_id' in meta and 'cmd_id' in cols and meta.get('cmd_id') is not None:
                # prepare update for provided keys (excluding id)
                update_cols = [c for c in use_cols if c != 'id' and c != 'cmd_id']
                if update_cols:
                    set_clause = ','.join([f"{c} = %s" for c in update_cols])
                    update_vals = [Json(meta.get(c)) if c in ('params', 'result') else meta.get(c) for c in update_cols]
                    update_vals.append(meta.get('cmd_id'))
                    sql = f"UPDATE command_logs SET {set_clause} WHERE cmd_id = %s"
                    cur.execute(sql, update_vals)
                    conn.commit()
                    return None
            # otherwise re-raise
            raise
    finally:
        conn.close()


def update_command_status(cmd_id: str = None, device_id: str = None, status: str = None, result = None):
    """
    更新 command_logs 的执行状态。

    优先按 cmd_id 精确更新；如果没有 cmd_id，则退化为更新该设备最近一条
    pending/sent 记录，用于兼容回调侧只能拿到 device_id 的情况。
    """
    if not cmd_id and not device_id:
        return 0
    conn = get_conn()
    try:
        cur = conn.cursor()
        # 优先按 cmd_id 精确更新，避免误更新同设备上的其他命令。
        if cmd_id:
            # build set clause
            sets = []
            vals = []
            if status is not None:
                sets.append('status = %s')
                vals.append(status)
            if result is not None:
                sets.append('result = %s')
                # result 写入 json/jsonb 字段时统一走 Json 适配。
                vals.append(Json(result))
            if not sets:
                return 0
            vals.append(cmd_id)
            sql = f"UPDATE command_logs SET {', '.join(sets)}, updated_at = NOW() WHERE cmd_id = %s"
            cur.execute(sql, vals)
            conn.commit()
            return cur.rowcount

        # 如果没有 cmd_id，只能退化为按 device_id 匹配最近一条“进行中”命令。
        cur.execute("SELECT id FROM command_logs WHERE device_id = %s AND status IN ('sent','pending') ORDER BY send_ts DESC NULLS LAST, created_at DESC NULLS LAST LIMIT 1", [device_id])
        row = cur.fetchone()
        if not row:
            return 0
        rec_id = row[0]
        sets = []
        vals = []
        if status is not None:
            sets.append('status = %s')
            vals.append(status)
        if result is not None:
            sets.append('result = %s')
            vals.append(Json(result))
        if not sets:
            return 0
        vals.append(rec_id)
        sql = f"UPDATE command_logs SET {', '.join(sets)}, updated_at = NOW() WHERE id = %s"
        cur.execute(sql, vals)
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def insert_campaign_publish_logs(
    campaign_id: str,
    version: str,
    results: list,
    batch_id: str = None,
) -> int:
    """
    Persist per-device publish results for audit/retry.
    Returns number of inserted rows.
    """
    conn = get_conn()
    try:
        cur = conn.cursor()
        # Keep this self-contained so local environments do not need manual migration first.
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS campaign_publish_logs (
                id BIGSERIAL PRIMARY KEY,
                campaign_id TEXT NOT NULL,
                batch_id TEXT,
                version TEXT,
                device_id TEXT NOT NULL,
                ok BOOLEAN NOT NULL,
                error TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )

        # Best-effort migration for existing tables.
        try:
            cur.execute("ALTER TABLE campaign_publish_logs ADD COLUMN IF NOT EXISTS batch_id TEXT")
        except Exception:
            pass

        inserted = 0
        for r in results or []:
            cur.execute(
                """
                INSERT INTO campaign_publish_logs (campaign_id, batch_id, version, device_id, ok, error)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    campaign_id,
                    batch_id,
                    version,
                    r.get("device_id"),
                    bool(r.get("ok")),
                    r.get("error"),
                ),
            )
            inserted += 1
        conn.commit()
        return inserted
    finally:
        conn.close()


def get_latest_failed_campaign_devices(campaign_id: str) -> list:
    """
    Return failed device_ids from the latest publish batch for a campaign.
    """
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT to_regclass('public.campaign_publish_logs')
            """
        )
        if not cur.fetchone()[0]:
            return []

        # Prefer explicit batch grouping when available.
        try:
            cur.execute(
                """
                SELECT batch_id
                FROM campaign_publish_logs
                WHERE campaign_id = %s AND batch_id IS NOT NULL
                ORDER BY created_at DESC
                LIMIT 1
                """,
                [campaign_id],
            )
            row = cur.fetchone()
        except Exception:
            row = None

        if row and row[0]:
            cur.execute(
                """
                SELECT DISTINCT device_id
                FROM campaign_publish_logs
                WHERE campaign_id = %s AND batch_id = %s AND ok = false
                """,
                [campaign_id, row[0]],
            )
            return [r[0] for r in cur.fetchall()]

        # Fallback for historical rows without batch_id: use the latest 5-second window.
        cur.execute(
            """
            WITH latest AS (
                SELECT max(created_at) AS ts
                FROM campaign_publish_logs
                WHERE campaign_id = %s
            )
            SELECT DISTINCT l.device_id
            FROM campaign_publish_logs l, latest
            WHERE l.campaign_id = %s
              AND latest.ts IS NOT NULL
              AND l.created_at >= latest.ts - interval '5 seconds'
              AND l.ok = false
            """,
            [campaign_id, campaign_id],
        )
        return [r[0] for r in cur.fetchall()]
    finally:
        conn.close()


def ensure_campaign_tables(cur) -> None:
    """
    Create campaign-related base tables/indexes if they do not exist.
    This keeps local/dev environments bootstrappable without manual SQL steps.
    """
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS campaigns (
            campaign_id TEXT PRIMARY KEY,
            name TEXT,
            creator_id TEXT,
            status TEXT NOT NULL DEFAULT 'draft',
            schedule_json JSONB NOT NULL,
            target_device_groups JSONB,
            start_at TIMESTAMPTZ,
            end_at TIMESTAMPTZ,
            version TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_campaigns_status ON campaigns(status)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_campaigns_updated_at ON campaigns(updated_at DESC)")


def list_campaign_publish_logs(campaign_id: str, limit: int = 100, offset: int = 0) -> list:
    """
    List publish logs for a campaign, newest first.
    """
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            """
            SELECT to_regclass('public.campaign_publish_logs')
            """
        )
        if not cur.fetchone()[0]:
            return []

        cur.execute(
            """
            SELECT campaign_id, batch_id, version, device_id, ok, error, created_at
            FROM campaign_publish_logs
            WHERE campaign_id = %s
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
            """,
            [campaign_id, limit, offset],
        )
        return cur.fetchall()
    finally:
        conn.close()


def mark_campaign_retry_batch(campaign_id: str, source_batch_id: str) -> bool:
    """
    Mark a source publish batch as retried once.
    Returns True if this is the first mark, False if already marked before.
    """
    if not source_batch_id:
        return True
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS campaign_retry_batches (
                id BIGSERIAL PRIMARY KEY,
                campaign_id TEXT NOT NULL,
                source_batch_id TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                UNIQUE (campaign_id, source_batch_id)
            )
            """
        )
        cur.execute(
            """
            INSERT INTO campaign_retry_batches (campaign_id, source_batch_id)
            VALUES (%s, %s)
            ON CONFLICT (campaign_id, source_batch_id) DO NOTHING
            """,
            [campaign_id, source_batch_id],
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def insert_campaign_version(campaign_id: str, version: str, schedule_json: dict) -> int:
    """
    Save a campaign version snapshot for history/rollback.
    """
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS campaign_versions (
                id BIGSERIAL PRIMARY KEY,
                campaign_id TEXT NOT NULL,
                version TEXT NOT NULL,
                schedule_json JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                UNIQUE (campaign_id, version)
            )
            """
        )
        cur.execute(
            """
            INSERT INTO campaign_versions (campaign_id, version, schedule_json)
            VALUES (%s, %s, %s)
            ON CONFLICT (campaign_id, version)
            DO UPDATE SET schedule_json = EXCLUDED.schedule_json, created_at = now()
            """,
            [campaign_id, version, Json(schedule_json)],
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def list_campaign_versions(campaign_id: str, limit: int = 50, offset: int = 0) -> list:
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            """
            SELECT campaign_id, version, schedule_json, created_at
            FROM campaign_versions
            WHERE campaign_id = %s
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
            """,
            [campaign_id, limit, offset],
        )
        return cur.fetchall()
    finally:
        conn.close()


def get_campaign_version(campaign_id: str, version: str):
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            """
            SELECT campaign_id, version, schedule_json, created_at
            FROM campaign_versions
            WHERE campaign_id = %s AND version = %s
            LIMIT 1
            """,
            [campaign_id, version],
        )
        return cur.fetchone()
    finally:
        conn.close()


def get_existing_device_ids(device_ids: list) -> list:
    """
    Return subset of input device_ids that exist in devices table.
    """
    if not device_ids:
        return []
    conn = get_conn()
    try:
        cur = conn.cursor()
        sql = "SELECT device_id FROM devices WHERE device_id = ANY(%s)"
        cur.execute(sql, [device_ids])
        return [r[0] for r in cur.fetchall()]
    finally:
        conn.close()


def get_existing_material_ids(ids: list) -> list:
    """
    Return subset of input ids that exist in materials table.
    Tries `ad_id` first (if column exists), then falls back to `material_id`.
    """
    if not ids:
        return []
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'materials'")
        cols = {r[0] for r in cur.fetchall()}
        if 'ad_id' in cols:
            sql = "SELECT ad_id FROM materials WHERE ad_id = ANY(%s)"
        elif 'material_id' in cols:
            sql = "SELECT material_id FROM materials WHERE material_id = ANY(%s)"
        else:
            return []
        cur.execute(sql, [ids])
        return [r[0] for r in cur.fetchall()]
    finally:
        conn.close()
