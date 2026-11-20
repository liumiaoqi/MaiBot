# 配置系统的系统性问题（2026-11-20 抓包核查后登记）

> 最后更新：2026-11-20
> 状态：📚 参考（问题登记，待排期；不替代 `.shared/decisions/phase3_config_plan.md`）
> 来源：`agent_context_identity` 实现期间的抓包与逐层核查

## 背景

为排查「为什么价格那么高」，从 Burp 抓到的 `POST /chat/completions` 响应里看到 `"model": "deepseek-v4-pro"`。
按配置逐层核对后，暴露的不是单点 bug，而是**配置系统整体的「配置 → 生效」链路不可观测**。

## 问题清单（每条带证据）

### 1. 模型配置「以为改了、实际没改」

- `docker-config/mmc/model_config.toml` 里 `model_task_config.replyer.model_list = ["deepseek-v4-flash"]`；
- `butler_filter` 调用时 `task_name="replyer"`（`butler.py` 的 `generate_response_with_messages("replyer", ...)`）；
- 实际解析到 `deepseek-v4-pro-nonthink`，抓包确认 `"model": "deepseek-v4-pro"`。

原因：ZG-12 组件自治后，模型选择走 `@model_requirement` 声明 + `capabilities` + `prefer`（`model_config_port.resolve_by_capability`），`model_task_config` 不是主路径。`LLMServiceClient` 只传 `task_name="replyer"` 解析成 `{"text_generation"}`，没有应用 `ThinkingOrgan` 声明的 `prefer`，默认策略选中了 pro。

### 2. 前端编辑的不是权威源

`mingtang/src/features/config/components/use-model-config.ts` 支持编辑 `model_task_config`，但真正的 `declarations/prefer` 没有编辑入口。**用户在前端改模型，改完不生效**——不是前端坏了，是它改的地方已经不是权威源。

### 3. 配置分层：模板层与部署层靠手工同步

- 模板层：仓根 `config/bot_config.toml`（gitignored，随代码走，测试夹具与首启兜底）；
- 部署层：`docker-config/mmc/bot_config.toml`（运行真值，随机器走，手工维护）。

新增一个开关要同步：`AgentAutonomySectionConfig` → `AgentAutonomySnapshot` → `AppConfigPort` → 模板 toml → 部署 toml，**五处**。本次 `agent_context_identity` 加两个开关，任何一处漏掉都是「静默默认值」。`version` 也是手工递增（本次 8.29.0→8.29.2）。

### 4. 开关默认值不显眼

两个开关首发默认 `false`；只有 `AgentOrchestrator.__init__` 的一行启动日志能看到当前值。用户不知道功能是否开启，也不知道当前生效的是模板层还是部署层的值。

### 5. 「配置写了但没人读」是反复出现的缺陷形态

- `set_*` 注入点零调用（历史 VLM 案例）；
- Port 白名单漏字段 → 快照取默认值；
- `model_task_config` 不是权威源；
- 前端编辑旧路径。

这些都是同一类：**配置存在 ≠ 配置生效**，且没有统一的「生效值 + 来源」自检。

### 6. 缺乏「配置 → 生效」的观测面

为查一个模型名，需要逐层 grep：`model_config_port` → `model_registry` → `declarations` → `prompt_builder`。没有一处能回答「这个任务最终会用哪个模型、为什么」。

## 建议（按优先级）

1. **配置生效摘要**：启动时打印关键开关的「当前值 + 来源（模板/部署/环境变量）」，默认值不隐藏。
2. **模型选择单一入口**：前端要么编辑 `declarations/prefer`（权威源），要么明确标注「只读/仅旧路径」；`model_task_config` 的语义在 UI 上写清楚。
3. **分层 diff 门禁**：启动/CI 对比模板层与部署层字段集合，缺字段告警（不是静默回退）。
4. **配置生效测试**：每个 Port 字段一条「非默认值 → 经 Port 读回」断言（本次已有 `test_agent_context_identity_flags.py` 的形态，可推广）。

## 与既有文档的关系

- 不重复 `2026-11-19-config-composition-system.md`（自由组合系统）——那篇讲「怎么组织配置」，本篇讲「配置为什么不生效」。
- 不重复 `2026-11-19-phase3-config-decisions.md`（六项收尾）——那篇讲迁移路径，本篇是新增的**可观测性债**。
- `2026-11-19-model-config-format-layer.md`（按格式分层）与本篇互补：那篇讲模型配置的组织，本篇讲模型选择的权威源与前端错位。

## 本次已顺带修掉的

- `save_speaker_change` 的 `record_id` 用秒级时间戳，同一秒写两条会 `UNIQUE constraint failed`；已改 `uuid7`（提交 `32d062043`）。
- 模型配置：从注册表移除两个 `deepseek-v4-pro` 模型，让候选只剩 flash（部署副本手工改动，未入 git）。

## 验证方式

- 抓包：同一会话发消息后看 `messages` 的 `role` 分布与 system prompt 自述段人称；
- 日志：`[agent_autonomy] context_identity=... self_narration_first_person=...` 与 `[context_attribution] viewer=...`；
- DB：`mai_messages.sender_type / sender_agent_id` 可查。