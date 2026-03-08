# 广告策略数据库与前端页面设计说明

本说明用于前后端对齐：策略如何存库、前端页面如何展示。

## 1) 数据库表设计

### `campaigns`（策略主表）

- 作用：策略列表/详情主数据，保存当前生效的 `schedule_json`
- 主键：`campaign_id`
- 关键字段：
  - `name`, `creator_id`, `status`, `version`
  - `schedule_json`（JSONB）
  - `target_device_groups`（JSONB，设备列表）
  - `created_at`, `updated_at`

### `campaign_versions`（版本快照）

- 作用：版本历史与回滚
- 唯一键：`(campaign_id, version)`
- 关键字段：
  - `campaign_id`, `version`, `schedule_json`, `created_at`

### `campaign_publish_logs`（发布日志）

- 作用：发布结果审计、失败重试
- 关键字段：
  - `campaign_id`, `batch_id`, `version`, `device_id`, `ok`, `error`, `created_at`

## 2) 前端页面建议

### A. 策略列表页

- 展示：`campaign_id`, `name`, `status`, `version`, `updated_at`
- 操作：查看详情、发布、查看日志、版本管理
- 接口：`GET /api/v1/campaigns/`

### B. 策略详情页

- 展示：
  - 基础信息（`name/creator_id/status/version`）
  - `schedule_json`（格式化 JSON）
  - `target_device_groups`
- 操作：导出 `schedule-config`、导出 `edge-schedule`
- 接口：
  - `GET /api/v1/campaigns/{campaign_id}`
  - `GET /api/v1/campaigns/{campaign_id}/schedule-config`
  - `GET /api/v1/campaigns/{campaign_id}/edge-schedule`

### C. 发布日志页

- 展示：`batch_id/device_id/ok/error/created_at`，并显示 `total/success/failed`
- 操作：失败重试
- 接口：
  - `GET /api/v1/campaigns/{campaign_id}/publish-logs`
  - `POST /api/v1/campaigns/{campaign_id}/retry-failed`

### D. 版本管理页

- 展示：`version`, `created_at`
- 操作：回滚（可选立即发布）
- 接口：
  - `GET /api/v1/campaigns/{campaign_id}/versions`
  - `POST /api/v1/campaigns/{campaign_id}/rollback`

### E. 策略创建页

- 输入：`ads_list`, `devices_list`, `time_rules`, `download_base_url`
- 支持紧急插播：`time_rules.interrupts[]`
- 接口：`POST /api/v1/campaigns/strategy`

## 3) 与端侧格式关系

- 控制面格式：`/schedule-config`
- 端侧格式：`/edge-schedule`（含 `global_config`、`interrupts`、`time_slots`、兜底 `slot_id=99`）
