# Campaign 常见问题与排障

## 1) `503 database unavailable`

现象：

- 创建策略、查询策略、发布策略接口返回 `503`

排查：

1. 检查 Postgres 是否启动、连接参数是否正确（`PG_HOST/PG_PORT/PG_USER/PG_PASSWORD/PG_DB`）。
2. 调用 `GET /api/debug/db/ping` 验证数据库连通性。
3. 本地联调可临时设置 `ENABLE_MEMORY_FALLBACK=true`。

---

## 2) `502 gateway delivery failed`

现象：

- 发布/回滚/重试接口返回 `502`

排查：

1. 确认 Go 网关服务在线，`GATEWAY_URL` 可访问。
2. 检查设备是否在线（Redis 在线态与网关连接态）。
3. 在发布日志接口查看设备级 `error` 字段定位失败原因。

---

## 3) `400 publish validation failed`

现象：

- 发布前校验失败，响应包含 `detail.errors`

常见原因：

- `playlist` 为空
- 广告 `id` 重复
- `slots` 非法或重叠
- `target_device_groups` 为空
- 素材/设备在数据库中不存在

---

## 4) `retry-failed` 不再执行（幂等）

现象：

- 返回 `idempotent=true`、`source batch already retried`

说明：

- 同一 `source_batch_id` 已重试过一次，系统按幂等规则阻止重复重试。
- 若确需再次重试，建议触发新一轮 `publish` 生成新 `batch_id`。

---

## 5) 端侧格式不匹配

现象：

- 端侧 `SyncSchedule` 解析失败

排查：

1. 使用 `GET /api/v1/campaigns/{campaign_id}/edge-schedule` 导出端侧格式，不要用控制面格式。
2. 确认返回包含：
   - `global_config`
   - `interrupts`
   - `time_slots`
   - 兜底 `slot_id=99`
