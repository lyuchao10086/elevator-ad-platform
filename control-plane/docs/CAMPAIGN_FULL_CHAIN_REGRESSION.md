# Campaign 全链路回归清单

目标：一次性验证策略模块从生成到回滚重试的主流程可用。

## 回归路径

1. `POST /api/v1/campaigns/strategy`
2. `GET /api/v1/campaigns/{campaign_id}/edge-schedule`
3. `POST /api/v1/campaigns/{campaign_id}/publish`
4. `GET /api/v1/campaigns/{campaign_id}/publish-logs`
5. `GET /api/v1/campaigns/{campaign_id}/versions`
6. `POST /api/v1/campaigns/{campaign_id}/rollback` (`publish_now=true`)
7. `POST /api/v1/campaigns/{campaign_id}/retry-failed`

## 关键检查点

- strategy 返回 `campaign_id`，状态为 `draft`
- edge-schedule 包含：
  - `global_config`
  - `interrupts`
  - `time_slots`
  - 默认兜底 `slot_id=99`
- publish 返回 `batch_id` 与设备级 `results`
- publish-logs 可看到成功/失败统计
- versions 至少有一条记录
- rollback 成功后可返回发布结果
- retry-failed 对同 `source_batch_id` 幂等（重复调用不重复重试）

## 自动化用例

运行：

```bash
cd control-plane
python -m pytest -c pytest.ini tests/api/test_campaigns_flow.py
```

重点用例：

- `test_campaign_full_chain_regression_flow`
