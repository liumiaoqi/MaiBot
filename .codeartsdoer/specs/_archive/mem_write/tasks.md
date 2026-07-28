# 核心→记忆写入链路优化 — 合并版编码任务清单

> 合并 CodeArts + Claude Code 两份 SSD 的最优方案。CC 贡献安全修复和结构清理，CA 贡献统一路径和架构创新。

## 依赖关系总览

```
批次1(安全修复) ──→ 批次2(结构清理) ──→ 批次3(统一路径+语义补全) ──→ 批次4(错误暴露+链路追踪)
                                                                              ↓
                                                                    批次5(异步写入队列)
                                                                              ↓
                                                                    批次6(调用方迁移+智能体体验写入)
                                                                              ↓
                                                                    批次7(清理废弃)
```

---

## 批次 1: 安全修复（低风险，高收益）— 来源: CC

### 1.1 timeout_ms 生效

- [ ] `src/A_memorix/host_service.py` — 移除 `del timeout_ms`（约 L184），用 `asyncio.wait_for()` 包裹 handler 调用
- [ ] 为不同操作类型设置合理默认超时（查询 10s，写入 30s，管理操作 120s）

**验收**：`timeout_ms=1` 触发 `asyncio.TimeoutError`；正常调用不受影响

**风险**：低

### 1.2 external_id 幂等检查

- [ ] `src/A_memorix/core/sdk_memory_kernel.py` 的 `ingest_text()` 开头新增 `metadata_store.get_external_memory_ref(external_id)` 检查
- [ ] 已存在时返回 `MemoryWriteResult(success=True, skipped_ids=[external_id])`

**验收**：连续两次相同 external_id 写入，第二次返回 skipped

**风险**：低

### 1.3 ChatSummaryWritebackService 失败游标更新

- [ ] `src/services/chat_summary_writeback.py` — 写入失败后仍然更新 `last_trigger_message_count`
- [ ] 新增 `_consecutive_failures` 计数器，连续 3 次失败后跳过本次触发阈值

**验收**：模拟 ingest_summary 失败，确认不会死循环重试

**风险**：低

### 1.4 队列背压

- [ ] `PersonFactWritebackService.enqueue()` 和 `ChatSummaryWritebackService.enqueue()` 改用 `await queue.put()` 替代 `put_nowait()`
- [ ] 设置 5 秒超时，超时时 log warning

**验收**：填满队列（maxsize=1 测试），确认调用不被静默丢弃

**风险**：低

---

## 批次 2: 结构清理（低风险）— 来源: CC

### 2.1 _coerce_* 去重

- [ ] 新建 `src/core/memory_utils.py`，移动 `_coerce_search_result`、`_coerce_write_result`、`_coerce_profile_result` 到此
- [ ] `src/services/memory_service.py` 和 `src/A_memorix/core/migration/migration_router.py` 改为 import 共享函数
- [ ] 移除 `MigrationRouter.__init__` 的 `coerce_search_result`/`coerce_write_result` 注入参数

**验收**：ruff check 通过；grep 确认 `_coerce_*` 来源唯一

**风险**：低

### 2.2 AgentMemoryAdapter 依赖注入

- [ ] `src/maisaka/agent_interaction/memory/adapter.py` — `AgentMemoryAdapter.__init__` 新增 `memory_port: MemoryServicePort` 参数
- [ ] 删除 `memory_port` 属性的懒创建 `AMemorixMemoryServicePort()` 逻辑
- [ ] 在 `InteractionEngine.__init__` 处创建并注入

**验收**：grep 确认无 `AMemorixMemoryServicePort()` 直接新建（适配器创建处除外）

**风险**：低

### 2.3 host_service.invoke() 分派字典化

- [ ] 将 `src/A_memorix/host_service.py` 的 ~30 个 if-elif 分支提取为独立 `_handle_*()` 函数
- [ ] 构建 `_DISPATCH: dict[str, Callable]` 字典映射
- [ ] `invoke()` 改为字典查找 + 调用
- [ ] 每个 handler 明确列出接受的参数名，不用 `**{k:v}` 透传

**验收**：所有现有 component_name 调用正常工作（容器启动 + LLM 请求 + 嵌入）

**风险**：中 — 大范围重构 host_service，需逐分支验证

---

## 批次 3: 统一写入路径 + 语义补全（低~中风险）— 来源: CA

### 3.1 新增 ObserveRequest 数据类 + 扩展 MemoryWriteResult

- [ ] `src/core/types.py` — 新增 `ObserveRequest` frozen dataclass：text(str)、valence(str="neutral")、timestamp(float|None)、source_id(str)、session_id(str)、agent_id(str)、participants(tuple[str,...])、tags(tuple[str,...])、metadata(dict[str,Any])
- [ ] `src/core/types.py` — `MemoryWriteResult` 新增 `pending: bool = False` 和 `trace_id: str = ""` 字段
- [ ] 同步更新 `MemoryWriteResult.to_dict()`

**验收**：`ObserveRequest(text="test", valence="positive", participants=("Alice","Bob"))` 正常构造且不可变

**风险**：低

### 3.2 MemoryServicePort 新增 observe_experience()

- [ ] `src/core/protocols.py` — `MemoryServicePort` 新增 `observe_experience()` 方法，签名：
  ```python
  async def observe_experience(self, *, text: str, valence: str = "neutral",
      timestamp: float | None = None, source_id: str = "", session_id: str = "",
      agent_id: str = "", participants: list[str] | None = None,
      tags: list[str] | None = None, metadata: dict[str, Any] | None = None
  ) -> MemoryWriteResult
  ```

**验收**：Protocol 类型检查通过；所有实现类需补全

**风险**：低

### 3.3 AMemorixMemoryServicePort 实现 observe_experience()

- [ ] `src/core/adapters/memory_service.py` — 实现 `observe_experience()`，调用 `memory_service.observe()`
- [ ] **不 catch Exception**，让异常上浮

**验收**：异常不被吞没，直接上浮到调用方

**风险**：低

### 3.4 MemoryService 新增 observe()

- [ ] `src/services/memory_service.py` — 新增 `observe()` 方法，调用 `self._invoke("observe", payload)`
- [ ] 使用 `_coerce_write_result()` 转换返回值

**验收**：`memory_service.observe(text="test")` 正常调用 host_service observe 分支

**风险**：低

### 3.5 host_service observe 分支补全语义参数

- [ ] `src/A_memorix/host_service.py` — observe 分支补全 `agent_id`、`participants`、`tags`、`metadata` 参数从 payload 提取并传递给 `kernel._memory_field.observe()`
- [ ] 当前仅传递 5 个参数，扩展到 9 个

**验收**：`host_service.invoke("observe", {"text": "test", "agent_id": "silver_wolf", "participants": ["Alice"]})` 时 MemoryField 收到完整参数

**依赖**：3.6、3.7

**风险**：低

### 3.6 Observer.observe() 签名扩展

- [ ] `src/A_memorix/core/connectionist/observer.py` — `observe()` 新增可选参数：`agent_id: str = ""`、`participants: list[str] | None = None`、`tags: list[str] | None = None`、`metadata: dict[str, Any] | None = None`
- [ ] `agent_id` 传递给 Trace 创建（作为写入方视角）
- [ ] `participants` 作为概念提取上下文提示（追加到 text 末尾）
- [ ] `tags` 和 `metadata` 存储到 Trace 扩展属性

**验收**：`observer.observe("test", agent_id="silver_wolf", participants=["Alice"])` 不报错

**风险**：中 — Observer 是核心写入逻辑

### 3.7 MemoryField.observe() 签名扩展

- [ ] `src/A_memorix/core/connectionist/memory_field.py` — `observe()` 新增同 3.6 的可选参数，透传到 Observer

**验收**：参数正确透传

**风险**：低

### 3.8 MigrationRouter.ingest_text() NEW_INDEPENDENT 分支补全字段传递

- [ ] `src/A_memorix/core/migration/migration_router.py` — NEW_INDEPENDENT 分支补全 `agent_id/participants/tags/metadata/valence` 传递给 `memory_field.observe()`
- [ ] 当前仅传递 3 个字段，扩展到 7 个

**验收**：MigrationRouter 传递完整参数到 MemoryField

**依赖**：3.7

**风险**：低

---

## 批次 4: 错误暴露 + 链路追踪（低风险）— 来源: CA

### 4.1 observe_experience() 异常上浮

- [ ] 确认 `src/core/adapters/memory_service.py` 的 `observe_experience()` 不 catch Exception（3.3 已实现）
- [ ] `ingest_text()` 保留 catch（向后兼容），日志级别从 warning 提升到 error

**验收**：LLM 不可用时 `observe_experience()` 抛异常；`ingest_text()` 日志为 ERROR

**风险**：低

### 4.2 写入链路 trace_id

- [ ] `src/core/adapters/memory_service.py` — `observe_experience()` 生成 UUID trace_id（`uuid.uuid4().hex[:12]`）
- [ ] 设置到 `MemoryWriteResult.trace_id`，通过 source_id 传递到下游日志

**验收**：日志中可按 trace_id 追踪完整写入链路

**风险**：低

### 4.3 MemoryService.observe() 错误暴露

- [ ] `src/services/memory_service.py` — `observe()` 不 catch Exception
- [ ] `_invoke()` 返回异常信息时构造含 detail 的失败结果

**验收**：host_service 不可用时 observe 抛出异常或返回含 detail 的失败结果

**风险**：低

---

## 批次 5: 异步非阻塞写入（中风险）— 来源: CA

### 5.1 新增 AsyncWriteQueue

- [ ] `src/A_memorix/core/connectionist/async_write_queue.py` — 新增异步写入队列
  - `__init__(self, observer: Observer, maxsize: int = 100)`
  - `async def start(self)` / `async def stop(self)`
  - `async def enqueue(...) -> MemoryWriteResult` — 入队立即返回 pending
  - `async def _consumer(self)` — 后台消费，失败重试 1 次
- [ ] 队列满时返回 `MemoryWriteResult(success=False, detail="write_queue_full")`
- [ ] 重试失败时 ERROR 日志含文本摘要

**验收**：队列正常消费；满时不崩溃；重试逻辑正确

**风险**：中

### 5.2 MemoryField.observe() 集成 AsyncWriteQueue

- [ ] `src/A_memorix/core/connectionist/memory_field.py` — `__init__()` 创建 AsyncWriteQueue
- [ ] 新增 `start_async_queue()` 方法
- [ ] `observe()` 新增 `async_write: bool = True` 参数：True→入队，False→同步
- [ ] SDKMemoryKernel 初始化后调用 `start_async_queue()`

**验收**：`observe(async_write=True)` 耗时 < 5ms；`async_write=False` 行为不变

**依赖**：5.1

**风险**：中

### 5.3 host_service observe 适配异步模式

- [ ] `src/A_memorix/host_service.py` — observe 分支传递 `async_write` 参数（默认 True）

**验收**：默认异步返回 pending 结果

**依赖**：5.2

**风险**：低

---

## 批次 6: 调用方迁移 + 智能体体验写入（中风险）— 来源: CA

### 6.1 person_info.py 迁移

- [ ] `src/person_info/person_info.py` — `_writeback_person_fact()` 从 `memory_service.ingest_text()` 迁移到 `MemoryServicePort.observe_experience()`
- [ ] 参数映射：external_id→source_id, source_type→tags, chat_id→session_id, person_ids→participants

**验收**：人物事实写回正常，不再直接调用 memory_service.ingest_text()

**依赖**：批次3

**风险**：中

### 6.2 dream.py 迁移

- [ ] `src/maisaka/subagent/agents/dream.py` — 从 `self._memory_service.ingest_text()` 迁移到 `MemoryServicePort.observe_experience()`
- [ ] 参数映射同 6.1

**验收**：梦境合并写入正常

**依赖**：批次3

**风险**：中

### 6.3 AgentMemoryAdapter 迁移到 observe_experience()

- [ ] `src/maisaka/agent_interaction/memory/adapter.py` — `_write_single()` 和 `propagate_memory()` 中的 `ingest_text()` 替换为 `observe_experience()`
- [ ] 参数映射同 6.1

**验收**：交互记忆写入正常

**依赖**：批次3 + 2.2

**风险**：中

### 6.4 host_service migration_ingest_text 标记废弃

- [ ] `src/A_memorix/host_service.py` — `migration_ingest_text` 分支添加 DeprecationWarning，内部重定向到 observe

**验收**：调用时出现 DeprecationWarning，功能不受影响

**风险**：低

### 6.5 新增 ExperienceWriter 体验写入器

- [ ] `src/maisaka/agent_autonomy/experience_writer.py` — 新增：
  - `should_write(result: ThinkResult) -> bool` — 纯规则门控（REPLY+text>10字 / INTENTIONAL+summary>20字 → 写入）
  - `write_experience(result, session_id, agent_id, emotion_state) -> None` — 构造摘要调用 observe_experience()，fire-and-forget
  - `_build_summary()` — 结构化体验摘要（非内心独白原文）
  - `_emotion_to_valence()` — 情绪→valence 映射

**验收**：门控规则正确；摘要不含内心独白原文；异常不阻塞

**风险**：中

### 6.6 Orchestrator 集成 ExperienceWriter

- [ ] `src/maisaka/agent_autonomy/orchestrator.py` — `__init__()` 创建 ExperienceWriter（需 MemoryServicePort 注入）
- [ ] 思考完成后 `should_write()` 判定，True 则 `asyncio.create_task(write_experience())`

**验收**：思考后关键体验被写入；不增加回复延迟

**依赖**：6.5

**风险**：中

### 6.7 VitalityManager 心跳可选写入

- [ ] `src/maisaka/agent_autonomy/vitality_manager.py` — 状态显著变化时（standby→active）写入环境感知体验

**验收**：状态跃迁时记忆写入；待命不产生琐碎记忆

**依赖**：6.5

**风险**：低

---

## 批次 7: 清理与废弃（低风险）— 来源: CA

### 7.1 ingest_text 全链路标记废弃

- [ ] `src/core/protocols.py` — `MemoryServicePort.ingest_text()` 添加 `# DEPRECATED: 使用 observe_experience() 替代`
- [ ] `src/core/adapters/memory_service.py` — `AMemorixMemoryServicePort.ingest_text()` 添加 `warnings.warn`
- [ ] `src/A_memorix/core/migration/migration_router.py` — `ingest_text()` 添加 `warnings.warn`
- [ ] `src/services/memory_service.py` — `MemoryService.ingest_text()` 添加 `warnings.warn`

**验收**：调用 ingest_text 时出现 DeprecationWarning

**风险**：低

### 7.2 更新文档

- [ ] `AGENTS.md` — MemoryServicePort 描述新增 observe_experience()
- [ ] `.codeartsdoer/rule/MaiBot智能体自主性架构.mdc` — 核心接口层表格更新
- [ ] 记忆系统范式迁移进展章节更新

**验收**：文档与代码实际状态一致

**风险**：低

### 7.3 ruff TID251 检查

- [ ] `ruff check src/core/ src/maisaka/agent_autonomy/ --select TID251` 确认零违规
- [ ] 确认 observe_experience() 路径无核心直接导入 A_memorix 内部模块

**验收**：ruff TID251 检查通过

**风险**：低

---

## 统计

| 批次 | 子任务数 | 风险 | 来源 |
|------|---------|------|------|
| 1 安全修复 | 4 | 低 | CC |
| 2 结构清理 | 3 | 低~中 | CC |
| 3 统一路径+语义补全 | 8 | 低~中 | CA |
| 4 错误暴露+链路追踪 | 3 | 低 | CA |
| 5 异步写入队列 | 3 | 中 | CA |
| 6 调用方迁移+体验写入 | 7 | 中 | CA |
| 7 清理废弃 | 3 | 低 | CA |
| **合计** | **31** | | |