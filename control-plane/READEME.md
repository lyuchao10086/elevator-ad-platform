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
