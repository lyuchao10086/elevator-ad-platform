# 云端广告下发改造说明

## 1. 文档目的

本文档用于说明本次 `control-plane` 推送中与广告下发链路相关的两次提交，方便团队成员快速了解：

- 本次改动解决了什么问题
- 云端当前的最终架构是什么
- 新增了哪些接口
- 旧的发布行为发生了什么变化
- 当前已验证到什么程度

对应提交如下：

1. `b93f21f` `feat(control-plane): add device-level schedule and material pull APIs`
2. `00a523c` `refactor(control-plane): remove push-based publish delivery`

---

## 2. 改造背景

这次改造的目标，是让云端严格对齐新的文档架构要求：

- 云端不再主动把排期推送到网关或端侧
- 云端只负责把 `campaign` 转换为设备可拉取的 `device-level schedule`
- 云端同时提供素材元数据和素材下载接口，供网关按需拉取
- “发布”在云端侧只表示“某个版本已成为当前已发布版本”，不再表示“已经主动推送成功”

换句话说，最终架构已经从“云端 push 到网关/设备”切换为“网关按设备 pull 云端”。

---

## 3. 最终架构结论

本次两次提交完成后，`control-plane` 当前的广告下发链路如下：

1. 后台创建或更新 `campaign strategy`
2. 云端保存 `schedule_config`，并可导出兼容端侧的 `edge_schedule`
3. 调用 `publish` 后，云端只做校验并将该 `campaign` 标记为 `published`
4. 网关通过设备维度接口拉取当前设备的最新已发布排期
5. 网关通过素材接口获取素材元数据和下载地址
6. 网关/端侧自行完成缓存、预下载、校验和离线播放

本次推送只覆盖云端 `control-plane`。网关和端侧本身的拉取、缓存、SQLite 落地、md5 校验、播放日志等逻辑不在这次改动范围内。

---

## 4. 第一次提交说明

### 提交信息

- Commit: `b93f21f`
- 标题: `feat(control-plane): add device-level schedule and material pull APIs`

### 主要工作

第一次提交的核心目标，是让云端具备“被网关拉取”的能力。

### 4.1 新增设备级拉取接口

新增了 `gateway` 端点，面向网关暴露以下能力：

- `GET /api/v1/gateway/devices/{device_id}/schedule`
  - 返回该设备当前应使用的已发布排期
  - 默认返回 `schedule-config` 结构
  - 支持 `?format=edge-schedule` 返回兼容现有端侧结构

- `GET /api/v1/gateway/devices/{device_id}/bundle`
  - 返回一个设备级 bundle
  - 包含：
    - `schedule`
    - `schedule_config`
    - `edge_schedule`
    - `assets`

- `GET /api/v1/gateway/devices/{device_id}/materials`
  - 返回该设备当前排期所需素材列表

- `GET /api/v1/gateway/materials/by-ad/{ad_id}`
  - 通过广告 ID 查询素材元数据与下载地址

- `GET /api/v1/gateway/materials/{material_id}`
  - 通过素材 ID 查询素材元数据

- `GET /api/v1/gateway/materials/{material_id}/file`
  - 下载素材文件

### 4.2 云端完成 `campaign -> device-level schedule` 转换

第一次提交把现有 `campaign.schedule_json` 结构化为设备可消费的排期输出，主要包含两种形式：

- `schedule-config`
  - 按 README 中约定的 JSON 播放清单格式输出
- `edge-schedule`
  - 兼容现有终端 `SyncSchedule()` 使用的结构

这样可以同时满足：

- 文档要求的标准播放清单格式
- 现有端侧兼容需求

### 4.3 增加素材下载信息输出

在设备级 bundle 和素材元数据接口中，补充了素材相关信息，例如：

- `material_id`
- `ad_id`
- `file_name`
- `md5`
- `type`
- `duration_sec`
- `size_bytes`
- `download_url`
- `metadata_url`
- `source_url`
- `file_exists`

云端在这里提供的是“素材信息 + 下载入口”，不再承担主动下发动作。

### 4.4 增加按设备查找最新已发布策略能力

在数据库服务层增加了“按设备查询当前最新已发布 campaign”的能力，用于支撑网关设备维度拉取。

---

## 5. 第二次提交说明

### 提交信息

- Commit: `00a523c`
- 标题: `refactor(control-plane): remove push-based publish delivery`

### 主要工作

第二次提交的核心目标，是把旧的 push 发布能力从 `control-plane` 主链路中移除，让整个架构严格变成 pull-only。

### 5.1 移除主动推送排期逻辑

移除后，云端不再通过旧逻辑向设备或网关发送 `UPDATE_SCHEDULE` 一类的远程命令。

被移除的内容包括：

- 主动推送排期的 helper
- 基于推送结果的批次记录逻辑
- 基于推送日志的幂等判断逻辑
- 基于失败设备的 retry 重试逻辑

### 5.2 重新定义 `publish`

现在的 `publish` 行为是：

1. 读取目标 `campaign`
2. 校验 `schedule_json`、目标设备、素材引用是否合法
3. 保存版本快照
4. 将该活动状态标记为 `published`
5. 返回 pull 模式下的发布结果

它不再做以下事情：

- 不再主动推送到网关
- 不再主动推送到设备
- 不再生成推送结果批次

### 5.3 重新定义 `rollback`

`rollback` 现在分为两种语义：

- `publish_now = false`
  - 仅切换 `campaign` 当前版本
  - 活动保持 `draft`
  - 不会被网关当作当前已发布策略拉取

- `publish_now = true`
  - 切换到指定版本
  - 完成校验后直接标记为 `published`
  - 仍然是 pull 模式，不做主动下发

### 5.4 `publish-logs` 与 `retry-failed` 退化为兼容接口

因为架构已经改成 pull-only，这两个接口不再具备原来的业务含义：

- `GET /campaigns/{campaign_id}/publish-logs`
  - 现在返回 pull 模式下的兼容响应
  - 标记为 `deprecated`
  - 不再返回真实推送日志

- `POST /campaigns/{campaign_id}/retry-failed`
  - 现在返回 pull 模式下的 no-op 响应
  - 标记为 `deprecated`
  - 不再执行失败设备重推

这样做的目的是避免旧调用方直接报错，同时明确告诉调用方：该能力在新架构下已经不适用。

### 5.5 重写测试用例到 pull-only 语义

测试从旧的“推送成功/失败/重试”模型，收敛为新的“发布状态 + 设备拉取”模型，主要覆盖：

- `publish` 发布成功
- `publish` 校验失败
- `publish` pull 模式幂等
- `rollback(publish_now=true)` 发布成功
- `rollback(publish_now=false)` 不可被网关拉取
- `publish-logs` 兼容响应
- `retry-failed` no-op 响应
- 设备级 schedule 拉取
- 设备级 bundle 拉取
- 素材元数据与下载 URL 查询

---

## 6. 这两次提交合起来后的最终效果

本次两次提交合并后的实际效果如下：

### 云端已经具备的能力

- 能把 `campaign` 转换成设备级排期
- 能返回 README 风格的 `schedule-config`
- 能返回兼容现有终端的 `edge-schedule`
- 能按设备提供当前已发布排期
- 能返回素材元数据
- 能返回素材下载地址
- 能返回设备级排期 bundle
- 能以 pull-only 方式完成“发布”与“回滚发布”

### 云端已经移除的旧行为

- 不再主动 push 排期到网关
- 不再主动 push 排期到设备
- 不再维护推送批次日志作为主流程依据
- 不再基于失败设备执行重推

---

## 7. 影响到的主要文件

本次两次提交涉及的关键文件如下：

- `control-plane/app/api/v1/endpoints/gateway.py`
  - 新增网关拉取接口

- `control-plane/app/api/v1/endpoints/campaigns.py`
  - 将发布流程改为 pull-only

- `control-plane/app/api/v1/router.py`
  - 挂载 `/api/v1/gateway/*` 路由

- `control-plane/app/services/db_service.py`
  - 增加按设备获取最新已发布 campaign 的能力

- `control-plane/tests/api/test_campaigns_flow.py`
  - 测试收敛到 pull-only 模型

---

## 8. 对外可直接说明的接口清单

如果需要向其他同事快速说明“云端这次到底提供了什么”，可以直接使用下面这份接口清单：

### 网关拉取接口

- `GET /api/v1/gateway/devices/{device_id}/schedule`
- `GET /api/v1/gateway/devices/{device_id}/bundle`
- `GET /api/v1/gateway/devices/{device_id}/materials`
- `GET /api/v1/gateway/materials/by-ad/{ad_id}`
- `GET /api/v1/gateway/materials/{material_id}`
- `GET /api/v1/gateway/materials/{material_id}/file`

### 运营侧/后台相关接口

- `POST /api/v1/campaigns/strategy`
- `GET /api/v1/campaigns/{campaign_id}/schedule-config`
- `GET /api/v1/campaigns/{campaign_id}/edge-schedule`
- `POST /api/v1/campaigns/{campaign_id}/publish`
- `POST /api/v1/campaigns/{campaign_id}/rollback`
- `GET /api/v1/campaigns/{campaign_id}/versions`

### 兼容保留但已弱化的接口

- `GET /api/v1/campaigns/{campaign_id}/publish-logs`
- `POST /api/v1/campaigns/{campaign_id}/retry-failed`

---

## 9. 当前验证情况

已完成的验证如下：

- 语法校验通过
- `control-plane/tests/api/test_campaigns_flow.py` 全量通过

执行命令：

```powershell
E:\Anaconda\envs\elevator-cp\python.exe -m pytest -c pytest.ini tests/api/test_campaigns_flow.py -q
```

结果：

- `18 passed`

备注：

- pytest 运行时有一个 `.pytest_cache` 写权限 warning
- 该 warning 不影响测试结论

---

## 10. 一句话总结

这两次提交完成后，`control-plane` 已经把广告下发链路从“云端主动推送”正式收敛为“网关按设备主动拉取”，并补齐了设备级排期输出、素材下载信息输出以及 pull-only 发布语义。
