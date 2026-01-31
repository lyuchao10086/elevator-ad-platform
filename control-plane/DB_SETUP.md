# Database setup and local run (control-plane)

本文件说明如何配置本地 Postgres 与运行 control-plane 服务，用于让后端能读取 `devices` 表并为前端提供数据。

1. 在 `control-plane` 下创建数据库（例如 `elevator_ad`）并运行仓库中的 `db/init.sql`（或自行创建表）。

2. 配置环境变量（两种方式）：

- 临时（PowerShell）:
```powershell
$env:PG_HOST="localhost"
$env:PG_USER="postgres"
$env:PG_PASSWORD="your_password"
$env:PG_DB="elevator_ad"
```

- 永久：在 `control-plane` 目录创建 `.env` 文件，写入：
```
PG_HOST=localhost
PG_USER=postgres
PG_PASSWORD=your_password
PG_DB=elevator_ad
```

3. 安装运行依赖并启动服务：
```powershell
python -m pip install -r requirements.txt
python -m pip install psycopg2-binary
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

4. 验证数据库连接：
- 访问 `http://localhost:8000/api/debug/db/ping`，返回 `{"ok": true, "devices_count": N}` 表示连接成功并能读取 `devices` 表。

5. 前端（开发）已配置代理：`web/admin/.env.development` 中 `VITE_API_URL` 默认指向 `http://localhost:8000/api`，启动前端后，DeviceList 页面会请求 `GET /api/devices` 展示设备列表。

如果你的 Postgres 使用非默认端口、用户名或密码，请相应调整上述变量。
