# Cloud Backend (FastAPI)

本目录是电梯广告投放系统的云端控制平面（control-plane），负责：

- 设备管理（注册、状态、远程控制）
- 素材管理（上传、状态流转、转码回调）
- 广告策略管理（策略生成、发布、日志、版本与回滚）
- 对 Web 端与网关提供统一 API

---

## 技术栈

- Python >= 3.10
- FastAPI / Uvicorn
- Pydantic v2
- PostgreSQL（持久化）
- Redis（与网关联动）

---

## 目录结构

```text
control-plane/
├─ app/
│  ├─ main.py
│  ├─ api/v1/
│  │  ├─ router.py
│  │  └─ endpoints/
│  ├─ core/
│  ├─ schemas/
│  └─ services/
├─ data/
├─ docs/
├─ tests/
├─ pyproject.toml
├─ pytest.ini
├─ .env.example
└─ READEME.md
```

---

## 本地开发

### 1) 安装依赖（venv）

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
pip install fastapi uvicorn pydantic pydantic-settings
pip install requests redis python-multipart psycopg2-binary
pip install pytest pytest-asyncio httpx
```

### 2) 安装依赖（Conda，推荐 conda-forge）

```bash
conda create -n elevator-control-plane python=3.10 -y
conda activate elevator-control-plane
conda install -c conda-forge fastapi uvicorn pydantic pydantic-settings requests redis python-multipart psycopg2 pytest pytest-asyncio httpx -y
```

### 3) 启动服务

```bash
python -m uvicorn app.main:app --reload --port 8000
```

常用接口：

- `GET /health`
- `GET /api/debug/db/ping`
- `GET /api/v1/devices/remote/{device_id}/snapshot`
- `GET /api/v1/campaigns/{campaign_id}/schedule-config`（导出纯 `schedule_config`）
- `GET /api/v1/campaigns/{campaign_id}/edge-schedule`（导出端侧 `SyncSchedule` 专用 JSON）

数据库配置请参考：`control-plane/DB_SETUP.md`

---

## 测试

### 1) 运行全部测试

```bash
python -m pytest -c pytest.ini
```

### 2) 运行广告策略关键链路测试

```bash
python -m pytest -c pytest.ini tests/api/test_campaigns_flow.py
```

当前已覆盖：

- 策略生成（含 DB 故障 + fallback 行为）
- 发布成功路径
- 发布校验失败（400）
- 网关下发全失败（502）
- DB 不可用（503）
- 失败重试异常路径（503/502）
- 回滚发布成功路径
- publish / rollback 幂等行为
- 端侧导出结构校验（`edge-schedule`）
- 中断策略（interrupts）透传校验

---

## Campaign 存储模式（重要）

用于控制 Postgres 不可用时，是否允许内存兜底：

- `ENABLE_MEMORY_FALLBACK=true`（默认）：启用内存兜底，适合本地联调
- `ENABLE_MEMORY_FALLBACK=false`：禁用内存兜底，DB 不可用时返回 `503 database unavailable`

推荐：

- local/dev：`ENABLE_MEMORY_FALLBACK=true`
- staging/prod：`ENABLE_MEMORY_FALLBACK=false`

---

## 端侧导出格式（SyncSchedule）

`GET /api/v1/campaigns/{campaign_id}/edge-schedule` 返回端侧可直接消费的策略 JSON，核心字段：

- `policy_id`
- `effective_date`
- `download_base_url`
- `global_config`（`default_volume` / `download_retry_count` / `report_interval_sec`）
- `interrupts`
- `time_slots`

### 默认兜底策略

导出时会强制补齐默认兜底槽位：

- `slot_id=99`
- `time_range=00:00:00-23:59:59`
- `loop_mode=random`
- `priority=1`
- `volume=0`

### 紧急插播/霸屏策略（interrupts）

在创建策略时，可通过 `time_rules.interrupts` 传入，单项结构：

- `trigger_type`: `command` 或 `signal`
- `ad_id`: 中断广告 ID
- `priority`: 正整数（建议高于普通时段）
- `play_mode`: 如 `loop_until_stop`

---

## 当前进度（设备与内容管理 + 广告策略）

已完成：

- 素材上传与状态流转规则对齐
- 转码回调字段（type/output_path 等）对齐
- 设备注册入库与远程命令链路打通
- 广告策略核心闭环：
  - `POST /campaigns/strategy`
  - `GET /campaigns/{id}/schedule-config`
  - `GET /campaigns/{id}/edge-schedule`
  - `POST /campaigns/{id}/publish`
  - `GET /campaigns/{id}/publish-logs`
  - `GET /campaigns/{id}/versions`
  - `POST /campaigns/{id}/rollback`
  - `POST /campaigns/{id}/retry-failed`
- 发布前校验增强（素材、设备、时段、优先级、重复项）
- 错误语义标准化（400/404/502/503）
- 幂等一致性增强（publish/rollback 二次调用不重复下发）
- 端侧协议增强：`global_config`、`interrupts`、`time_slots` 及默认兜底 `slot_id=99`

待完成（下一步）：

- `retry-failed` 的更细粒度幂等约束（按批次重试行为再收敛）
- 端到端联调脚本再沉淀（gateway + redis + db）
- 最终交付文档整理（运行手册、故障排查、已知限制）

---

## 已知限制

- 当前 `retry-failed` 采用“同 `source_batch_id` 仅重试一次”的幂等策略；重复重试需新建发布批次。
- `edge-schedule` 的 `global_config` 仍为默认值模板，尚未完全参数化到策略输入。
- `interrupts` 已支持透传与校验，但高级触发策略（例如多级规则组合）尚未实现。

## 快速排障入口

- 数据库连通性：`GET /api/debug/db/ping`
- 策略发布日志：`GET /api/v1/campaigns/{campaign_id}/publish-logs`
- 端侧格式导出：`GET /api/v1/campaigns/{campaign_id}/edge-schedule`

---

## 参考文档

- 联调验收清单：`control-plane/docs/CAMPAIGN_E2E_CHECKLIST.md`
- 全链路回归清单：`control-plane/docs/CAMPAIGN_FULL_CHAIN_REGRESSION.md`
- 前端对接说明：`control-plane/docs/CAMPAIGN_API_FRONTEND_CONTRACT.md`
- 数据库与页面设计：`control-plane/docs/CAMPAIGN_DB_UI_SPEC.md`
- 常见问题排障：`control-plane/docs/CAMPAIGN_TROUBLESHOOTING.md`
- 数据库配置：`control-plane/DB_SETUP.md`
- 依赖定义：`control-plane/pyproject.toml`
