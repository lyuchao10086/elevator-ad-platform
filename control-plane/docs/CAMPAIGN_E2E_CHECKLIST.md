# 广告策略联调与验收清单

用于 4 天内项目汇报时的演示顺序，覆盖“可生成、可发布、可追踪、可回滚”闭环。

## 1. 环境准备

- 启动 `control-plane` 服务（`http://127.0.0.1:8000`）
- 启动 Go 网关（`GATEWAY_URL` 可访问）
- 启动 Redis（用于设备在线与命令链路）
- 启动 Postgres（建议）
- 环境变量确认：
  - `GATEWAY_URL`
  - `REDIS_HOST/REDIS_PORT/REDIS_DB/REDIS_PASSWORD`
  - `ENABLE_MEMORY_FALLBACK`

## 2. Swagger 演示路径

1) `POST /api/v1/campaigns/strategy`
- 期望：返回 `campaign_id`，`campaign_status=draft`，`schedule_config` 有 `playlist`

2) `GET /api/v1/campaigns/`
- 期望：能查到上一步创建的 campaign

3) `POST /api/v1/campaigns/{campaign_id}/publish`
- 期望：返回 `pushed/total`，并带 `batch_id`

4) `GET /api/v1/campaigns/{campaign_id}/publish-logs`
- 期望：有发布结果明细（设备维度成功/失败）

5) `GET /api/v1/campaigns/{campaign_id}/versions`
- 期望：至少有一个版本记录

6) `POST /api/v1/campaigns/{campaign_id}/rollback`
- body: `{"version":"xxx","publish_now":true}`
- 期望：返回 `published=true`，并输出发布结果

7) `POST /api/v1/campaigns/{campaign_id}/retry-failed`
- 期望：失败设备可重试；无失败设备时返回 `retried=0`

## 3. 关键异常验证（汇报加分项）

- `ENABLE_MEMORY_FALLBACK=false` + 断开 Postgres：
  - `POST /campaigns/strategy` 返回 `503 database unavailable`
- 发布参数校验：
  - 重复广告 id、无效 slots、空设备列表时返回校验错误

## 4. 自动化测试

在 `control-plane` 下执行：

```bash
python -m pytest -q
```

当前新增覆盖：

- strategy：DB 故障下内存兜底 / 禁用兜底返回 503
- publish：成功发布并记录日志
- rollback：按版本回滚并可立即发布
