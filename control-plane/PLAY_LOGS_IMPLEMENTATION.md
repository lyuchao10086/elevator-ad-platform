## 播放日志（Play Logs）端到端实现

### 概述

本文档说明了从设备端到云端的完整播放日志流处理方案的实现细节。

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          完整数据流架构                                   │
└─────────────────────────────────────────────────────────────────────────┘

Edge Device (端侧)
  │
  ├─ SQLite表: log
  │   ├─ log_id: 唯一标识符
  │   ├─ device_id: 设备ID
  │   ├─ ad_id: 广告ID
  │   ├─ duration_ms: 播放时长
  │   ├─ status_code: 状态码
  │   ├─ uploaded: 上传标签(0/1)
  │   └─ 其他字段...
  │
  └─ 每30秒上传一次（WebSocket）
       │
       ▼
Cloud Gateway (网关)
  │
  ├─ handleLogReport() 接收日志
  ├─ 补充时间戳、设备IP
  └─ 发送到Kafka主题: play_logs
       │
       ▼
Kafka Topic: play_logs (消息队列)
  │
  ├─ 分区策略: device_id (同一设备的日志都进同一分区)
  ├─ 消息格式: 
  │   {
  │     "log_id": "9f8c-12d4-55e1-4a2b",
  │     "device_id": "ELEV_001",
  │     "ad_id": "AD_NIKE_2026",
  │     "duration_ms": 15000,
  │     "status_code": 200,
  │     ...
  │   }
  └─ 消息保留时间: 默认7天
       │
       ▼
Control-Plane (云端)
  │
  ├─ Kafka消费者 (kafka_consumer.py)
  │   ├─ 消费play_logs主题
  │   ├─ 反序列化JSON
  │   ├─ 字段规范化和类型转换
  │   └─ 批量处理（50条/批）
  │
  ├─ 数据库操作 (db_service.py)
  │   ├─ 调用 insert_or_update_ad_log()
  │   ├─ UPSERT模式: INSERT ... ON CONFLICT
  │   └─ 已存在的日志会被更新（覆盖）
  │
  └─ PostgreSQL数据库
      │
      └─ ad_logs表
         ├─ log_id: 唯一约束
         ├─ device_id, ad_id, duration_ms, status_code...
         └─ 索引: device_id, start_time, created_at...
         
前端查询
  │
  └─ GET /api/v1/ad_logs
     └─ 从ad_logs表读取日志数据
```

---

## 部分1: 端侧（Edge）实现 ✅ 已完成

### Edge表结构（SQLite）

```sql
CREATE TABLE IF NOT EXISTS log (
    log_id TEXT PRIMARY KEY,              -- 16字符UUID
    device_id TEXT NOT NULL,              -- 设备ID
    ad_id TEXT,                           -- 广告ID
    ad_file_name TEXT NOT NULL,           -- 文件名
    start_time TIMESTAMP WITH TIME ZONE,  -- 播放开始时间
    end_time TIMESTAMP WITH TIME ZONE,    -- 播放结束时间
    duration_ms INT,                      -- 播放时长(毫秒)
    status_code SMALLINT,                 -- 状态码
    status_msg TEXT,                      -- 状态描述
    created_at BIGINT,                    -- Unix时间戳
    device_ip TEXT,                       -- 设备IP
    firmware_version TEXT,                -- 固件版本
    uploaded INTEGER DEFAULT 0            -- 上传标签(0=未, 1=已)
);
```

### Edge上传策略

- **上传频率**: 每30秒钟一次
- **批量大小**: 每次最多50条未上传的日志
- **传输方式**: WebSocket长连接
- **消息格式**:
```json
{
  "type": "log",
  "payload": [
    {
      "log_id": "9f8c-12d4-55e1-4a2b",
      "device_id": "ELEV_001",
      "ad_id": "AD_NIKE_2026",
      "ad_file_name": "ads/nike_ad.mp4",
      "start_time": "2026-03-19 10:30:00",
      "end_time": "2026-03-19 10:30:15",
      "duration_ms": 15000,
      "status_code": 200,
      "status_msg": "Play Success",
      "created_at": 1709815005,
      "device_ip": "192.168.1.105",
      "firmware_version": "1.0.0"
    }
    // ... 最多49条更多记录
  ]
}
```

---

## 部分2: 网关（Gateway）实现 ✅ 已完成

### 网关日志接收

**位置**: `cloud/internal/gateway/handler.go`

- **端点**: WebSocket 连接 `/ws`
- **处理函数**: `handleLogReport()`
- **职责**:
  1. 解析来自端侧的日志JSON
  2. 补充网关侧信息（时间戳、IP等）
  3. 发送到Kafka主题

### 网关→Kafka

**Topic**: `play_logs`
**Partitioning Key**: `device_id` (同一设备所有日志都进同一分区，保证顺序)

### 网关配置

**文件**: `cloud/configs/.env.example`
```env
KAFKA_BROKERS=10.12.58.42:9092
KAFKA_PLAYLOG_TOPIC=play_logs
```

---

## 部分3: 云端（Control-Plane）实现 ✅ 新增

### 3.1 数据库表定义

**文件**: `control-plane/db/init_play_logs.sql`

```sql
CREATE TABLE IF NOT EXISTS ad_logs (
    id BIGSERIAL PRIMARY KEY,
    log_id TEXT NOT NULL UNIQUE,          -- 端侧日志ID（唯一约束用于去重）
    device_id TEXT NOT NULL,
    ad_id TEXT,
    ad_file_name TEXT,
    start_time TIMESTAMPTZ,               -- 设备端播放开始时间
    end_time TIMESTAMPTZ,                 -- 设备端播放结束时间
    duration_ms BIGINT,                   -- 实际播放时长
    status_code SMALLINT,                 -- 状态码（200=成功）
    status_msg TEXT,
    device_ip TEXT,
    firmware_version TEXT,
    created_at TIMESTAMPTZ,               -- 设备端创建时间戳
    updated_at TIMESTAMPTZ DEFAULT now(), -- 云端收到时间
    
    -- 其他字段（预留用途）
    expected_md5 TEXT,
    actual_md5 TEXT,
    is_valid BOOLEAN,
    billing_status TEXT
);

-- 优化查询的索引
CREATE INDEX idx_ad_logs_log_id ON ad_logs(log_id);
CREATE INDEX idx_ad_logs_device_id ON ad_logs(device_id);
CREATE INDEX idx_ad_logs_start_time ON ad_logs(start_time DESC);
CREATE INDEX idx_ad_logs_created_at ON ad_logs(created_at DESC);
```

### 3.2 Kafka消费者服务

**文件**: `control-plane/app/services/kafka_consumer.py`

#### 功能特性

1. **消费者配置**
   - Consumer Group: `control-plane-play-logs`
   - Topic: `play_logs`
   - Auto Offset Reset: `earliest` (从最早消息开始)
   - Auto Commit: 启用

2. **消息处理**
   - 批量处理: 每50条消息一批
   - 反序列化: JSON → Python dict
   - 字段规范化: 时间戳转换、类型检查
   - 去重: 基于 log_id 的UPSERT

3. **时间戳处理**
   - 支持Unix时间戳（秒或毫秒）
   - 支持ISO格式字符串
   - 自动检测并转换

4. **错误处理**
   - 单条记录失败不阻止其他记录处理
   - 自动重连Kafka broker
   - 回退重试机制

#### 关键方法

```python
class KafkaPlayLogConsumer:
    def start_consuming(self, batch_size: int = 50):
        """Start consuming and persisting logs to database"""
    
    def _normalize_log_record(self, log_data: Dict) -> Dict:
        """Normalize log record and handle type conversions"""
    
    def _insert_log_record(self, conn, log_record: Dict) -> bool:
        """Insert single record with UPSERT"""
```

### 3.3 后台任务管理

**文件**: `control-plane/app/services/background_tasks.py`

```python
class BackgroundTaskManager:
    def start_kafka_consumer(self) -> bool:
        """在后台线程启动Kafka消费者"""
    
    def stop_kafka_consumer(self):
        """优雅关闭消费者"""
```

### 3.4 应用生命周期管理

**文件**: `control-plane/app/main.py` (已修改)

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application startup and shutdown"""
    # 启动: 启动Kafka消费者后台任务
    task_manager = get_task_manager()
    task_manager.start_kafka_consumer()
    
    yield  # 应用运行
    
    # 关闭: 优雅停止消费者
    task_manager.stop_kafka_consumer()
```

### 3.5 数据库操作封装

**文件**: `control-plane/app/services/db_service.py` (新增函数)

```python
def insert_or_update_ad_log(log_record: dict) -> bool:
    """
    插入或更新单个日志记录（UPSERT模式）
    - 如果log_id不存在: 新增
    - 如果log_id已存在: 更新所有字段
    """

def batch_insert_ad_logs(log_records: list) -> int:
    """批量处理多个日志记录"""
```

---

## 配置和运行

### 环境变量配置

**文件**: `control-plane/.env`

```env
# PostgreSQL
PG_HOST=localhost
PG_PORT=5432
PG_USER=postgres
PG_PASSWORD=123456
PG_DB=elevator_ad

# Kafka
KAFKA_BROKERS=10.12.58.42:9092
KAFKA_PLAYLOG_TOPIC=play_logs

# Redis (可选)
REDIS_HOST=10.12.58.42
REDIS_PORT=6379
```

### 依赖安装

1. **更新依赖**:
```bash
pip install -e .
# 或
pip install kafka-python>=2.0.0
```

2. **初始化数据库**:
```sql
-- 在PostgreSQL中执行
psql -U postgres -d elevator_ad -f control-plane/db/init_play_logs.sql
```

### 启动应用

```bash
cd control-plane

# 方式1: 使用uvicorn
uvicorn app.main:app --host 0.0.0.0 --port 8000

# 方式2: 使用主应用脚本
python -m app.main
```

**应用会自动**:
1. 启动FastAPI服务器（端口8000）
2. 在后台启动Kafka消费者线程
3. 消费者开始从Kafka读取日志并写入数据库
4. 前端可通过 `/api/v1/ad_logs` 查询日志

### 监控和日志

应用会输出的日志:
```
2026-03-19 10:30:00 - INFO: Starting control-plane application...
2026-03-19 10:30:00 - INFO: Starting Kafka consumer in background thread...
2026-03-19 10:30:01 - INFO: Kafka consumer thread started
2026-03-19 10:30:01 - INFO: Kafka consumer started successfully, waiting for messages...
2026-03-19 10:30:05 - DEBUG: Received log message: 9f8c-12d4-55e1-4a2b
2026-03-19 10:30:05 - INFO: Batch insert: 50/50 records inserted
```

---

## 前端查询日志

### 查询所有日志

```bash
curl "http://localhost:8000/api/v1/ad_logs?limit=50&offset=0"
```

**响应**:
```json
{
  "total": 1234,
  "items": [
    {
      "id": 1,
      "log_id": "9f8c-12d4-55e1-4a2b",
      "device_id": "ELEV_001",
      "ad_id": "AD_NIKE_2026",
      "ad_file_name": "ads/nike_ad.mp4",
      "start_time": "2026-03-19T10:30:00+08:00",
      "end_time": "2026-03-19T10:30:15+08:00",
      "duration_ms": 15000,
      "status_code": 200,
      "status_msg": "Play Success",
      "device_ip": "192.168.1.105",
      "firmware_version": "1.0.0",
      "created_at": "2026-03-19T10:30:00+08:00",
      "updated_at": "2026-03-19T10:30:05+08:00",
      "completion_rate": 1.0,
      "play_result": "完播"
    },
    ...
  ]
}
```

### 按设备过滤

```bash
curl "http://localhost:8000/api/v1/ad_logs?device_id=ELEV_001&limit=50"
```

### 按时间范围过滤

```bash
curl "http://localhost:8000/api/v1/ad_logs?from_ts=2026-03-19%2010:00:00&to_ts=2026-03-19%2011:00:00"
```

### 查询特定日志详情

```bash
curl "http://localhost:8000/api/v1/ad_logs/9f8c-12d4-55e1-4a2b"
```

---

## 故障排查

### 问题1: Kafka消费者不工作

**症状**: 日志没有持久化到数据库

**检查**:
1. Kafka服务是否运行?
   ```bash
   telnet 10.12.58.42 9092
   ```

2. 环境变量是否正确?
   ```bash
   echo $KAFKA_BROKERS
   ```

3. 网关是否发送了消息到Kafka?
   ```bash
   # 使用kafka-console-consumer检查
   kafka-console-consumer.sh --bootstrap-servers 10.12.58.42:9092 \
     --topic play_logs --from-beginning
   ```

4. 检查应用日志:
   ```bash
   # 在启动时查看是否有Kafka连接错误
   ```

### 问题2: 日志没有完全入库

**症状**: 某些字段为NULL

**原因**: 端侧没有发送这个字段，或格式不匹配

**解决**: 
- 检查端侧发送的JSON格式
- 检查字段命名（区分大小写）
- 某些字段原本就支持NULL值

### 问题3: 同一个日志重复插入

**症状**: 同一个log_id的记录出现多次

**原因**: UPSERT配置错误，应该是UPDATE而不是INSERT

**检查**: 确认数据库中log_id有UNIQUE约束

```sql
-- 检查约束
SELECT constraint_name, constraint_type
FROM information_schema.table_constraints
WHERE table_name = 'ad_logs';
```

---

## 性能优化

### 批量处理参数调整

如果每秒日志消息很多（>1000条），可以调整：

```python
# 在kafka_consumer.py中
self.consumer = KafkaConsumer(
    ...
    max_poll_records=100,  # 从默认50增加到100
)
```

### 数据库连接池

生产环境建议使用连接池（如pgBouncer）而不是每次创建新连接

### 日志表分区

对于超大规模日志（日均百万条），可以按时间进行表分区：

```sql
CREATE TABLE ad_logs_2026_03 PARTITION OF ad_logs
    FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');
```

---

## 完整流程总结

1. ✅ **端侧**: 设备应用将播放完成的日志存储到SQLite，每30秒上传一批未上传的日志
2. ✅ **网关**: 网关接收日志，补充元数据，发送到Kafka主题
3. ✅ **消费**: 云端Kafka消费者读取消息，规范化数据
4. ✅ **持久化**: 使用UPSERT将日志写入PostgreSQL ad_logs表
5. ✅ **查询**: 前端通过API从ad_logs表读取日志展示

这个方案的优点：
- **解耦**: 各部分独立，通过Kafka解耦
- **可靠性**: 使用UPSERT保证幂等性，日志不重复
- **实时性**: 从接收到持久化延迟<1秒
- **可扩展性**: Kafka可以轻松处理高并发
- **可追溯性**: 完整保留所有时间戳便于后续分析
