# 播放日志系统 - 快速参考指南

## 核心文件位置速查

| 模块 | 文件 | 功能 |
|------|------|------|
| **数据库** | `control-plane/db/init_play_logs.sql` | ad_logs表定义和索引 |
| **Kafka消费者** | `control-plane/app/services/kafka_consumer.py` | 从Kafka读取日志，写入DB |
| **后台任务** | `control-plane/app/services/background_tasks.py` | 后台线程管理 |
| **数据库操作** | `control-plane/app/services/db_service.py` | CRUD操作（新增两个函数）|
| **主应用** | `control-plane/app/main.py` | FastAPI应用+生命周期管理 |
| **依赖** | `control-plane/pyproject.toml` | kafka-python依赖 |
| **文档** | `control-plane/PLAY_LOGS_IMPLEMENTATION.md` | 完整实现文档 |

## 快速启动命令

### 1. 数据库初始化（仅首次）

```bash
cd control-plane

# 确保PostgreSQL正在运行
# 然后执行表创建脚本
psql -U postgres -d elevator_ad -f db/init_play_logs.sql

# 验证表创建成功
psql -U postgres -d elevator_ad -c "\dt ad_logs"
```

### 2. 安装依赖

```bash
cd control-plane

# 使用pip安装
pip install -e .

# 或单独安装kafka-python
pip install kafka-python>=2.0.0
```

### 3. 启动应用

```bash
cd control-plane

# 方式1: 直接运行（推荐开发环境）
python app/main.py

# 方式2: 使用uvicorn
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 方式3: 生产环境（使用gunicorn）
gunicorn -w 4 -k uvicorn.workers.UvicornWorker app.main:app --bind 0.0.0.0:8000
```

### 4. 验证系统运行

```bash
# 1. 检查应用健康状态
curl http://localhost:8000/health
# 预期: {"status": "ok"}

# 2. 查询日志（应为空或返回已有日志）
curl "http://localhost:8000/api/v1/ad_logs?limit=10"

# 3. 检查Kafka连接（查看应用日志）
# 日志中应该看到: "Kafka consumer started successfully, waiting for messages..."
```

## 环境变量配置

### .env文件示例

```env
# PostgreSQL连接
PG_HOST=localhost
PG_PORT=5432
PG_USER=postgres
PG_PASSWORD=123456
PG_DB=elevator_ad

# Kafka配置
KAFKA_BROKERS=10.12.58.42:9092
KAFKA_PLAYLOG_TOPIC=play_logs

# 可选: Redis（如果使用缓存）
REDIS_HOST=10.12.58.42
REDIS_PORT=6379
REDIS_PASSWORD=123456
```

## 监控命令

### 1. 查看日志消费进度

```bash
# 查看有多少条日志记录
psql -U postgres -d elevator_ad -c "SELECT COUNT(*) FROM ad_logs;"

# 查看最近的日志
psql -U postgres -d elevator_ad -c \
  "SELECT log_id, device_id, ad_id, created_at FROM ad_logs ORDER BY created_at DESC LIMIT 10;"

# 按设备统计日志数
psql -U postgres -d elevator_ad -c \
  "SELECT device_id, COUNT(*) as count FROM ad_logs GROUP BY device_id ORDER BY count DESC;"
```

### 2. 查看Kafka消费状态

```bash
# 检查消费者组状态
kafka-consumer-groups.sh --bootstrap-servers 10.12.58.42:9092 \
  --group control-plane-play-logs --describe

# 查看play_logs主题信息
kafka-topics.sh --bootstrap-servers 10.12.58.42:9092 \
  --topic play_logs --describe

# 手动消费消息验证（新终端）
kafka-console-consumer.sh --bootstrap-servers 10.12.58.42:9092 \
  --topic play_logs --from-beginning --max-messages 5
```

### 3. 应用日志分析

```bash
# 运行应用时查看日志（应该看到类似信息）:
# [2026-03-19 10:30:01] Starting Kafka consumer in background thread...
# [2026-03-19 10:30:01] Kafka consumer thread started
# [2026-03-19 10:30:01] Kafka consumer started successfully, waiting for messages...
# [2026-03-19 10:30:05] DEBUG: Received log message: 9f8c-12d4-55e1-4a2b
# [2026-03-19 10:30:05] INFO: Batch insert: 50/50 records inserted
```

## API接口速查

### 获取所有日志

```bash
# 基础查询
curl "http://localhost:8000/api/v1/ad_logs"

# 分页 (页码、每页数量)
curl "http://localhost:8000/api/v1/ad_logs?limit=50&offset=100"

# 按设备过滤
curl "http://localhost:8000/api/v1/ad_logs?device_id=ELEV_001"

# 按广告过滤
curl "http://localhost:8000/api/v1/ad_logs?ad_file_name=nike"

# 时间范围查询
curl "http://localhost:8000/api/v1/ad_logs?from_ts=2026-03-19%2010:00:00&to_ts=2026-03-19%2011:00:00"

# 通用搜索
curl "http://localhost:8000/api/v1/ad_logs?q=ELEV_001"
```

### 获取单条日志详情

```bash
curl "http://localhost:8000/api/v1/ad_logs/9f8c-12d4-55e1-4a2b"
```

## 故障排查速查

| 症状 | 可能原因 | 检查命令 |
|------|--------|--------|
| Kafka消费者不启动 | 缺少kafka-python包 | `pip list \| grep kafka` |
| 无法连接Kafka | Kafka服务未运行或地址错误 | `telnet 10.12.58.42 9092` |
| 无法连接PostgreSQL | 数据库服务未运行或凭证错误 | `psql -U postgres -h localhost` |
| ad_logs表不存在 | 初始化脚本未执行 | `psql -c "\dt ad_logs"` |
| 日志没有入库 | Kafka没有消息或消费者未运行 | 查看应用日志 |
| 日志重复出现 | log_id约束未生效 | `psql -c "SELECT COUNT(DISTINCT log_id) FROM ad_logs"` |
| 前端查不到日志 | ad_logs表为空或API配置错误 | `curl http://localhost:8000/api/v1/ad_logs` |

## 生产部署检查清单

- [ ] PostgreSQL数据库创建并初始化（运行了init_play_logs.sql）
- [ ] Kafka集群正常运行（3个broker推荐）
- [ ] 环境变量配置文件（.env）已创建
- [ ] kafka-python包已安装（pip install kafka-python>=2.0.0）
- [ ] 应用启动时Kafka消费者成功启动（检查日志）
- [ ] 端侧能连接到网关（WebSocket持续连接）
- [ ] 网关能发送消息到Kafka（检查Kafka日志）
- [ ] 第一条日志已成功写入ad_logs表
- [ ] 前端能通过API查询日志
- [ ] 日志查询性能满足要求（<1s）
- [ ] 配置日志轮转（防止磁盘满）
- [ ] 配置定期备份（数据安全）

## 性能指标参考

| 指标 | 目标 | 检查方式 |
|------|------|--------|
| 日志写入延迟 | <1s | 检查created_at和updated_at的差异 |
| 消费吞吐量 | >1000条/秒 | 测试期间查看日志写入速度 |
| 数据库查询 | <500ms | 使用explain analyze分析查询 |
| 内存使用 | <512MB | 监控应用进程内存 |

## 常见调试步骤

### 场景1: 完整日志流测试

```bash
# 终端1: 启动应用
cd control-plane && python app/main.py

# 终端2: 监看Kafka日志流
kafka-console-consumer.sh --bootstrap-servers 10.12.58.42:9092 \
  --topic play_logs --from-beginning

# 终端3: 监看数据库（每秒刷新）
watch -n 1 'psql -U postgres -d elevator_ad -c "SELECT COUNT(*) FROM ad_logs;"'

# 终端4: 测试到网关的日志上传（通过设备/网关自身）
# 或模拟发送日志到Kafka
kafka-producer.sh --broker-list 10.12.58.42:9092 --topic play_logs \
  <<EOF
{"log_id": "test-001", "device_id": "ELEV_TEST", "ad_id": "AD_TEST", "duration_ms": 5000, "status_code": 200}
EOF
```

### 场景2: 调试单个日志记录

```python
# 在Python REPL中测试
from app.services.db_service import insert_or_update_ad_log
from datetime import datetime

log_record = {
    'log_id': 'debug-001',
    'device_id': 'DEBUG_DEVICE',
    'ad_id': 'AD_DEBUG',
    'duration_ms': 10000,
    'status_code': 200,
    'status_msg': 'Test',
    'created_at': datetime.now(),
    'device_ip': '127.0.0.1',
    'firmware_version': '1.0.0'
}

success = insert_or_update_ad_log(log_record)
print(f"Insert result: {success}")
```

#### 场景3: 验证UPSERT行为

```bash
# 插入第一条记录
psql -U postgres -d elevator_ad -c \
  "INSERT INTO ad_logs (log_id, device_id, status_code) VALUES ('upsert-test', 'DEV1', 200);"

# 验证存在
psql -U postgres -d elevator_ad -c \
  "SELECT log_id, status_code FROM ad_logs WHERE log_id = 'upsert-test';"

# 调用UPSERT更新（模拟Kafka消费）
psql -U postgres -d elevator_ad -c \
  "INSERT INTO ad_logs (log_id, device_id, status_code, status_msg) VALUES ('upsert-test', 'DEV1', 200, 'Updated') \
   ON CONFLICT (log_id) DO UPDATE SET status_msg = 'Updated';"

# 验证更新
psql -U postgres -d elevator_ad -c \
  "SELECT log_id, status_msg FROM ad_logs WHERE log_id = 'upsert-test';"
```

## 升级和维护

### 添加新字段到ad_logs表

```sql
-- 1. 添加新列
ALTER TABLE ad_logs ADD COLUMN new_field TEXT;

-- 2. 更新消费代码处理新字段
-- - 修改kafka_consumer.py的_normalize_log_record()
-- - 修改db_service.py的insert_or_update_ad_log()

-- 3. 重启应用
```

### 删除过期日志（可选）

```sql
-- 删除30天前的日志
DELETE FROM ad_logs WHERE created_at < CURRENT_TIMESTAMP - INTERVAL '30 days';

-- 定期缩小表
VACUUM ad_logs;
```

### 备份日志数据

```bash
# 完整备份
pg_dump -U postgres elevator_ad > backup_$(date +%Y%m%d).sql

# 只备份ad_logs表
pg_dump -U postgres -t ad_logs elevator_ad > ad_logs_$(date +%Y%m%d).sql

# 恢复备份
psql -U postgres elevator_ad < backup_20260319.sql
```
