# Cloud Backend (FastAPI)

本目录为 **电梯广告投放系统 · 云端业务控制中心**，负责：

- 设备管理（注册 / 状态）
- 广告素材管理（上传 / 转码）
- 投放活动与策略生成（Campaign & Schedule）
- 为 Edge 端与 Web 端提供统一的 API 服务

当前阶段为 **FastAPI 项目骨架 + API 入口初始化**，不包含完整业务逻辑。

---

## 技术栈

- Python ≥ 3.10
- FastAPI
- Uvicorn
- Pydantic

后续计划接入：
- SQLAlchemy + PostgreSQL
- Celery + Redis（异步任务，如转码、日志处理）

---

## 目录结构说明

```text
control-plane/
├─ app/
│  ├─ main.py            # FastAPI 应用入口
│  ├─ api/               # API 路由层
│  │  └─ v1/
│  │     ├─ router.py    # v1 API 聚合
│  │     └─ endpoints/   # 各业务模块接口
│  ├─ core/              # 配置 / 安全 / 通用工具
│  ├─ db/                # 数据库连接与会话（预留）
│  ├─ models/            # ORM 模型（预留）
│  ├─ schemas/           # Pydantic 数据模型
│  ├─ services/          # 业务逻辑层
│  └─ tasks/             # 异步任务（Celery，预留）
├─ docker-compose.yml    # 本地开发依赖（预留）
├─ pyproject.toml        # Python 依赖定义
├─ .env.example          # 环境变量示例
└─ README.md
```

---

## 本地开发与调试

> 说明：所需环境依赖组可查看`pyproject.toml` 
> python环境下请先用 venv 创建隔离环境，然后按需安装依赖。
> 另外，也可以用conda配置依赖环境

### 1) 建议的基础依赖

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate

pip install fastapi uvicorn pydantic pydantic-settings
pip install requests redis python-multipart psycopg2-binary
```

#### Conda 环境（推荐 conda-forge）

```bash
conda create -n elevator-control-plane python=3.10 -y
conda activate elevator-control-plane
conda install -c conda-forge fastapi uvicorn pydantic pydantic-settings requests redis python-multipart psycopg2 -y
```

### 2) 启动服务（调试模式）

```bash
python -m uvicorn app.main:app --reload --port 8000
```

常用调试接口：
- `GET /health`：服务存活检查
- `GET /api/debug/db/ping`：数据库连接检查（需先配置 DB）
- `GET /api/v1/devices/remote/{device_id}/snapshot`：触发截图（需 Go 网关在线）

数据库与环境变量请参考：`control-plane/DB_SETUP.md`。

---

## 测试（当前为预留）

> 目前项目尚未包含 `tests/`，但建议按以下依赖与命令准备测试环境。

### 1) 测试依赖

```bash
pip install pytest pytest-asyncio httpx
```

### 2) 运行测试

```bash
python -m pytest -q
```

### 3) 推荐测试目录结构（建议）

```text
control-plane/
└─ tests/
   ├─ api/
   ├─ services/
   └─ conftest.py
```

### 4) 集成依赖提示

如测试依赖 Postgres / Redis，请先启动对应服务，并配置：
- `PG_HOST / PG_PORT / PG_USER / PG_PASSWORD / PG_DB`
- `REDIS_HOST / REDIS_PORT / REDIS_DB`

必要时可在 `tests/conftest.py` 中统一加载 `.env`。
