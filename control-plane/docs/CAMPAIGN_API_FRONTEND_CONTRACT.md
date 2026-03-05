# Campaign 前端对接说明（control-plane）

用于前端快速对接广告策略模块，覆盖主流程：生成、查询、发布、日志、版本、回滚、失败重试。

## 1. 基础信息

- Base URL（本地）：`http://127.0.0.1:8000/api/v1`
- Content-Type：`application/json`
- 统一资源：`/campaigns`

---

## 2. 接口清单

### 2.1 生成策略（创建草稿）

- `POST /campaigns/strategy`

请求体示例：

```json
{
  "ads_list": [
    {
      "id": "ad_101",
      "file": "coke_cny.mp4",
      "md5": "a1b2c3",
      "priority": 10,
      "slots": ["08:00-10:00", "17:00-19:00"]
    }
  ],
  "devices_list": ["dev_001", "dev_002"],
  "time_rules": {
    "name": "morning_campaign",
    "creator_id": "u_1"
  },
  "download_base_url": "https://oss.aliyun.com/ads/"
}
```

成功返回（200）关键字段：

- `campaign_id`
- `campaign_status`（`draft`）
- `persisted`（是否落库）
- `schedule_config`（含 `playlist`）

---

### 2.2 列表 / 详情

- `GET /campaigns/`
- `GET /campaigns/{campaign_id}`

前端常用字段：

- `campaign_id`
- `name`
- `status`
- `version`
- `target_device_groups`
- `schedule_json`
- `created_at` / `updated_at`

---

### 2.3 发布策略

- `POST /campaigns/{campaign_id}/publish`

成功（200）关键字段：

- `ok`
- `pushed` / `total`
- `batch_id`
- `results`（按设备）
- `idempotent`（可选，`true` 表示同版本同目标已发布，未重复下发）

失败语义：

- `400`：参数/校验失败（`detail.errors`）
- `404`：campaign 不存在
- `502`：网关下发全部失败
- `503`：数据库不可用（且禁用 fallback）

---

### 2.4 发布日志

- `GET /campaigns/{campaign_id}/publish-logs?limit=100&offset=0`

成功（200）关键字段：

- `campaign_id`
- `total`
- `success`
- `failed`
- `items[]`（包含 `batch_id`, `device_id`, `ok`, `error`, `created_at`）

---

### 2.5 版本历史

- `GET /campaigns/{campaign_id}/versions?limit=50&offset=0`

成功（200）关键字段：

- `total`
- `items[]`（`version`, `schedule_json`, `created_at`）

---

### 2.6 回滚版本

- `POST /campaigns/{campaign_id}/rollback`

请求体：

```json
{
  "version": "20260305_v1",
  "publish_now": true
}
```

成功（200）关键字段：

- `ok`
- `version`
- `published`
- `batch_id`（当 `publish_now=true`）
- `idempotent`（可选，表示该版本已发布到当前目标）

失败语义：

- `400`：回滚发布校验失败
- `404`：版本或 campaign 不存在
- `502`：网关回滚下发全部失败
- `503`：数据库不可用（且禁用 fallback）

---

### 2.7 重试失败设备

- `POST /campaigns/{campaign_id}/retry-failed`

成功（200）关键字段：

- `ok`
- `retried`
- `pushed`
- `batch_id`
- `results`

失败语义：

- `400`：重试前校验失败
- `404`：campaign 不存在
- `502`：网关重试下发全部失败
- `503`：查询失败日志失败 / 数据库不可用

---

## 3. 前端建议流程

1. 创建策略 -> 跳转详情页（拿 `campaign_id`）
2. 详情页展示 `schedule_json` 与目标设备
3. 点击发布 -> 展示 `pushed/total` 与设备结果
4. 发布后跳转日志页（按 `batch_id` 展示）
5. 版本页支持回滚，并在回滚成功后刷新日志
6. 重试失败按钮仅在 `failed > 0` 时可点击

---

## 4. 错误处理建议（前端）

- 400：展示后端返回的 `detail.errors` 列表
- 404：提示“策略不存在或已删除”
- 502：提示“网关下发失败，可稍后重试”
- 503：提示“后端依赖不可用（DB）”

---

## 5. 备注

- 当 `ENABLE_MEMORY_FALLBACK=true` 时，本地联调可在 DB 不可用时继续开发。
- 生产环境建议 `ENABLE_MEMORY_FALLBACK=false`，避免无持久化运行。
