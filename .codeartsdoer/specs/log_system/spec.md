# 日志与调试系统升级 — 需求规格

## 背景

CQ-2 完成后，全项目已统一 `get_logger`，structlog + JSONL + WebSocket 实时推送已就位。本阶段聚焦增量改进：动态级别调整、日志搜索/过滤、ThinkCycleLog 可视化。

## 需求

### L1：动态日志级别调整

**现状**：日志级别在启动时从 `bot_config.toml` 读取，运行时无法修改。排障时需重启容器才能把某模块从 INFO 调到 DEBUG。

**目标**：通过 WebUI API 运行时修改任意模块的日志级别，修改立即生效，重启后恢复配置文件默认值（不持久化到 toml）。

**验收标准**：
- [x] WebUI 提供 `GET /api/webui/log/levels` 返回所有模块当前级别
- [x] WebUI 提供 `PATCH /api/webui/log/levels` 修改指定模块级别，立即生效
- [x] 修改不持久化到配置文件，重启后恢复默认
- [x] 支持按模块前缀批量调整（如 `maisaka.*` 一键调 DEBUG）

### L2：日志搜索与过滤

**现状**：WebUI 日志查看器只能加载最近 100 条，无法按模块/级别/时间范围/关键词搜索。

**目标**：从 JSONL 文件中搜索历史日志，支持模块过滤、级别过滤、时间范围、关键词搜索。

**验收标准**：
- [x] WebUI 提供 `GET /api/webui/log/search` 支持查询参数：module、level、since、until、keyword、limit
- [x] 搜索从 JSONL 文件倒序读取，高效（不加载全部文件到内存）
- [x] 返回结果格式与 WebSocket 实时日志一致

### L3：ThinkCycleLog 可视化

**现状**：`ThinkCycleLog` 数据结构已定义（agent_id, session_id, cycle_id, trigger_source, action, silence_reason, thought_summary, duration_ms, llm_calls），但未在 WebUI 展示。

**目标**：WebUI 展示最近的思考循环日志，帮助理解智能体"在想什么"和"为什么沉默"。

**验收标准**：
- [x] 思考循环日志写入独立的 JSONL 文件（`logs/think_cycles_*.log.jsonl`）
- [x] WebUI 提供 `GET /api/webui/log/think-cycles` 查询最近的思考循环
- [x] 展示字段：时间、智能体、触发源、动作、沉默原因、耗时、LLM 调用数

## 不做的事

- 不重构 structlog 配置管线（已稳定）
- 不改 JSONL 文件格式（已与 WebSocket 推送对齐）
- 不做日志聚合/ELK 集成（过度工程）
- 不做远程调试 REPL（安全风险）