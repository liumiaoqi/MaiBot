# design: 核心→记忆写入链路优化

## 总体策略

按影响面和风险分 4 批次执行：低风险修复 → 去重 → 核心优化 → 高级特性。

---

## 批次 1: 安全修复（低风险，高收益）

### 1.1 timeout_ms 生效

**现状**：`host_service.invoke()` 第 184 行 `del timeout_ms`。

**方案**：用 `asyncio.wait_for()` 包裹 handler 调用。

```python
async def invoke(self, component_name, args=None, *, timeout_ms=30000):
    payload = args or {}
    kernel = await self._ensure_kernel()
    handler = _DISPATCH.get(component_name)
    if handler is None:
        return self._disabled_response(component_name)
    return await asyncio.wait_for(handler(kernel, payload), timeout=timeout_ms / 1000)
```

### 1.2 external_id 幂等检查

**现状**：ingest_text 不检查 external_id 是否已存在。

**方案**：在 `SDKMemoryKernel.ingest_text()` 开头调用 `metadata_store.get_external_memory_ref(external_id)`，若已存在则返回 skipped。

### 1.3 ChatSummaryWritebackService 失败游标更新

**现状**：ingest_summary 失败后游标不更新，每次消息都重试。

**方案**：写入失败时仍然更新 `last_trigger_message_count`，但记录连续失败次数。连续失败超过 3 次时跳过本次阈值，避免死循环。

### 1.4 分批队列背压

**现状**：`put_nowait()` + QueueFull 静默丢弃。

**方案**：改用 `await queue.put()` 带 5 秒超时。超时时 log warning 并 ack（不做无限制等待）。

---

## 批次 2: 结构清理

### 2.1 _coerce_* 去重

**现状**：`_coerce_search_result` 和 `_coerce_write_result` 各两份。

**方案**：提取为 `src/core/memory_utils.py` 的模块级函数，两边都 import 使用。移除 MigrationRouter.__init__ 的 coerce_* 注入参数。

### 2.2 AgentMemoryAdapter 依赖注入

**现状**：`AgentMemoryAdapter.memory_port` 属性懒创建 `AMemorixMemoryServicePort` 实例。

**方案**：改为构造函数注入 `memory_port: MemoryServicePort`，由外部传入。与现有 DI 模式一致。

### 2.3 host_service.invoke() 分派字典化

**现状**：~30 个 if 分支。

**方案**：用字典分派替代 if-elif 链。每个 handler 是 `async def(kernel, payload) -> Any` 的签名。

```python
_DISPATCH: dict[str, Callable] = {
    "search_memory": _handle_search_memory,
    "ingest_text": _handle_ingest_text,
    "migration_ingest_text": _handle_migration_ingest_text,
    ...
}
```

每个 handler 函数独立提取参数并验证，替代 `**{k:v}` 透传。

---

## 批次 3: 字段完整传递

### 3.1 扩展 connectionist observe 接口

**现状**：`memory_field.observe(text, source_id, session_id)` 只接受 3 个字段。

**方案**：扩展 `MemoryField.observe()` 和 `ObserveResult` 接受完整的记忆上下文。

新增 `ObservationContext` dataclass：
```python
@dataclass
class ObservationContext:
    text: str
    source_id: str = ""
    session_id: str = ""
    chat_id: str = ""
    person_ids: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    timestamp: float | None = None
```

`MigrationRouter._legacy_ingest()` 和 `memory_field.observe()` 同步接受此上下文。在 DUAL_WRITE 阶段不再只传 3 个字段。

---

## 批次 4: 异步非阻塞 LLM（低优先级）

### 4.1 mid_term.py 的 LLM 调用

**现状**：`build_mid_term_memory_message()` 阻塞等待 LLM。

**分析**：此调用在消息历史裁剪流程中被同步 await，改为 fire-and-forget 会影响"裁剪后上下文立即包含摘要"的语义。当前架构下这是一个已知取舍，不在本次优化范围内。**本次改为文档化问题**，待后续架构演进时处理。

### 4.2 PersonFactWritebackService LLM

**现状**：在 worker loop 中同步等待 `self._extractor.generate_response(prompt)`。

**方案**：改为 `asyncio.create_task()` fire-and-forget，将结果通过 Queue 回传或在回调中写入。如果 worker 需要阻塞等待 LLM 完成，则增加并发 worker 数量。

---

## 设计决策

1. **不合并 MigrationRouter 到 host_service** — Router 职责清晰（迁移感知路由），合并会增加 host_service 复杂度。
2. **不删除分类学路径** — MigrationAdapter 的 phase 机制正在使用中，贸然删除会导致连接主义不稳定时无回退路径。
3. **写入幂等性仅基于 external_id** — 不做 content hash 比较（成本太高）。
4. **批次 4 中 mid_term.py 仅文档化** — 其同步阻塞是当前架构的已知取舍，贸然改为异步会影响上下文构建的时序保证。
5. **AgentMemoryAdapter 注入改构造函数** — 与 ModelConfigPort 的注入模式保持一致。
