# spec: 核心→记忆写入链路优化

## 背景

MaiBot 的核心→A_memorix 写入链路经过多次迭代积累了技术债务。当前调用链为：

```
消费者 → AMemorixMemoryServicePort → memory_service → host_service.invoke() → MigrationRouter → 分类学/连接主义
```

链路中存在双路径混乱、语义损失、阻塞调用、错误吞没等 14 个问题。

## 核心能力需求

### 1. 统一写入入口

MigrationRouter 的 DUAL_WRITE 阶段同时写分类学和连接主义两条路径，调用者无法控制目标。需要统一写入入口，让 MigrationAdapter 的 phase 切换对上游透明，而不是在 DUAL_WRITE 时双写。

### 2. 字段完整传递

MigrationRouter.ingest_text() 传给连接主义 memory_field.observe() 时只保留了 text/source_id/session_id 三个字段，chat_id、person_ids、tags、metadata、entities、relations、timestamp、time_start、time_end、participants、respect_filter、user_id、group_id 全部丢弃。

### 3. 异步非阻塞 LLM

mid_term.py 的 build_mid_term_memory_message() 在线程内同步等待 llm_client.generate_response_with_messages()，阻塞智能体思考周期。memory_flow_service.py 的 PersonFactWritebackService._extract_facts() 同样在 async worker 内同步等待 LLM 调用。

### 4. 核心主动写入

核心缺乏主动写入记忆的能力，所有记忆写入依赖上层（maisaka）通过 MemoryServicePort 适配器间接发起。核心应在关键事件发生时主动写入记忆（如协议变更、会话状态变更等）。

### 5. 错误传播

当前错误处理模式为统一的 `except Exception: log + return fallback`，错误被静默吞没。写入失败时上游无法感知失败原因，只能看到 success=False。需要区分可恢复和不可恢复错误，可恢复的做有限重试，不可恢复的完整暴露给上游。

### 6. 消除代码重复

_coerce_search_result 和 _coerce_write_result 在 memory_service.py（类方法）和 migration_router.py（模块函数）中各有一份几乎完全相同的拷贝。需要提取为共享模块。

### 7. 消除字符串分发的巨型 if-elif

host_service.invoke() 用 ~30 个字符串 if 分支分派组件调用，每个 migration_* 函数用 `**{k:v}` 透传参数。无类型安全、无 IDE 支持、无参数校验。

### 8. timeout_ms 实际生效

host_service.invoke() 声明 timeout_ms 参数但执行 `del timeout_ms` 将其丢弃，所有调用无超时保护。需要让超时参数实际生效。

### 9. 写入幂等性

external_id 在写入前未做去重检查。store_person_memory_from_answer 用 MD5 生成 external_id，但 legacy ingest 路径不做重复校验。

### 10. 失败重试与游标更新

ChatSummaryWritebackService 写入失败后不更新 last_trigger_message_count 游标，导致每条后续消息都重新触发失败的写入。

### 11. 队列背压

PersonFactWritebackService 和 ChatSummaryWritebackService 的 asyncio.Queue 固定 256 条，满时 put_nowait 抛 QueueFull 被静默丢弃。无背压机制。

### 12. AgentMemoryAdapter 绕过适配器

AgentMemoryAdapter.memory_port 属性直接创建 AMemorixMemoryServicePort 实例，而不是通过依赖注入获取。这导致了双套适配器实例并行的混乱。

## 非功能需求

- 所有修改通过 ruff check 和 pyright/vscode 类型检查
- 写入性能不退化（P99 延迟不超过现有水平）
- 向后兼容：现有调用方无需修改即可继续工作
- AGENTS.md 约束全量遵守
