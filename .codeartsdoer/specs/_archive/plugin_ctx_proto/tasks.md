# SSD-8：插件上下文协议化 — 编码任务规划

## 迁移概览

| 批次 | 主题 | 负责人 | 任务数 |
|------|------|--------|--------|
| 1 | 基础设施搭建（Protocol + 适配器 + 注册点 + MaisakaRuntime 扩展 + 启动注册 + ruff 守卫） | CC | 6 |
| 2 | H4 消费方迁移（chat_bot 直接导入消除，main.py 已在批次 1 合并处理） | Codex | 3 |
| 3 | H5 消费方迁移（heartflow_manager 私有属性访问消除） | Codex | 2 |
| 4 | 验证与清理（ruff 全量验证 + 残留导入清理 + 适配器 __init__ 更新） | CX | 3 |

**消费方总计**：8 处直接导入（4 处 `chat_bot` + 4 处 `heartflow_manager`），其中 main.py 的 1 处 chat_bot 迁移合并到批次 1

**文件锁规则**：同一批次内文件互不重叠；跨批次文件锁在任务描述中标注。

---

## 1. 基础设施搭建（Protocol + 适配器 + 注册点 + MaisakaRuntime 扩展 + 启动注册 + ruff 守卫）

**负责人**：CC（Protocol 接口设计需首次正确，注册点模式需与 MemoryServicePort/LLMService 一致，ChatRuntime 签名修复需理解现有调用链）

**前置条件**：无

### 1.1 定义 MessageIngestionPort Protocol

- [ ] 在 `src/core/protocols.py` 中新增 `MessageIngestionPort` Protocol，定义 2 个异步方法签名：
  - `receive_message(self, message: SessionMessage) -> None`：接收并处理入站消息
  - `message_process(self, message_data: Dict[str, Any]) -> None`：处理 Platform IO 入站封装
  - 使用 `@runtime_checkable` 装饰器
  - 在 `TYPE_CHECKING` 块中导入 `SessionMessage`（来自 `src/chat/message_receive/message.py`）、`Dict`、`Any`（来自 `typing`）
  - Protocol 不暴露 `_ensure_started`、`_get_runtime_manager`、`echo_message_process`、`bot` 等内部方法/属性
  - **验收标准**：`isinstance(chat_bot_instance, MessageIngestionPort)` 返回 True（鸭子类型兼容）；方法签名与 design.md 2.2.2 完全一致；Protocol 不包含任何私有方法或内部字段
  - **文件锁**：`src/core/protocols.py`

### 1.2 扩展 ChatRuntime Protocol（3 个新方法 + 1 个签名修复）

- [ ] 在 `src/core/protocols.py` 的 `ChatRuntime` Protocol 中新增 3 个方法 + 修复 `enqueue_proactive_task` 签名：
  - **新增 `append_context_message`**：
    ```python
    def append_context_message(self, message: Any, *, source_kind: str = "plugin") -> int:
        """向聊天历史追加上下文消息。"""
    ```
  - **新增 `get_talk_frequency_adjust`**：
    ```python
    def get_talk_frequency_adjust(self) -> float:
        """获取当前回复频率倍率。"""
    ```
  - **新增 `adjust_talk_frequency`**：
    ```python
    def adjust_talk_frequency(self, frequency: float) -> None:
        """调整当前回复频率倍率。"""
    ```
  - **修复 `enqueue_proactive_task` 签名**：新增 `priority: str = ""` 参数（在 `reason` 之后、`metadata` 之前），返回类型从 `Optional[dict[str, Any]]` 改为 `dict[str, Any]`
  - **验收标准**：`MaisakaRuntime` 实例满足扩展后的 `ChatRuntime` Protocol（鸭子类型）；`enqueue_proactive_task` 签名与 `MaisakaRuntime.enqueue_proactive_task` 完全一致；新增 3 个方法签名与 design.md 2.2.2 完全一致
  - **文件锁**：`src/core/protocols.py`（与 1.1 同文件，同一批次内由 CC 统一处理）

### 1.3 实现 ChatBotMessageIngestionPort 适配器 + 注册点函数

- [ ] 在 `src/core/adapters/message_ingestion_port.py` 中实现适配器和注册点：
  - **ChatBotMessageIngestionPort 类**：
    - 构造函数接受 `chat_bot: ChatBot` 参数，存储为 `self._chat_bot`
    - `receive_message(self, message: SessionMessage) -> None`：直接委托到 `await self._chat_bot.receive_message(message)`
    - `message_process(self, message_data: Dict[str, Any]) -> None`：直接委托到 `await self._chat_bot.message_process(message_data)`
    - 零额外逻辑，不引入缓存、转换或延迟加载
  - **注册点函数**（与 `llm_service_port.py` 模式一致）：
    - `get_message_ingestion_port() -> MessageIngestionPort`：未注册时抛出 `RuntimeError("MessageIngestionPort 未注册，请先调用 set_message_ingestion_port()")`
    - `set_message_ingestion_port(port: MessageIngestionPort) -> None`：重复注册时覆盖并记录 warning 日志
    - `reset_message_ingestion_port() -> None`：清除全局实例（仅用于测试）
  - 模块级 `_provider: MessageIngestionPort | None = None` 变量
  - logger 命名空间：`core.adapters.message_ingestion_port`
  - **验收标准**：`ChatBotMessageIngestionPort` 满足 `MessageIngestionPort` Protocol；2 个方法返回值与直接调用 `chat_bot` 对应方法完全一致；注册点函数行为与 `get_llm_service()`/`set_llm_service()`/`reset_llm_service()` 一致
  - **文件锁**：`src/core/adapters/message_ingestion_port.py`

### 1.4 MaisakaRuntime 新增 append_context_message 和 get_talk_frequency_adjust 方法

- [ ] 在 `src/maisaka/runtime.py` 的 `MaisakaRuntime` 类中新增 2 个方法：
  - **`append_context_message(self, message: Any, *, source_kind: str = "plugin") -> int`**：
    - 委托到 `self._chat_history.append(message)`
    - 返回 `len(self._chat_history) - 1`（追加后的索引位置）
    - `source_kind` 参数保留供未来扩展使用（当前 `_chat_history.append()` 不使用，但消息对象自身携带 `source_kind`）
  - **`get_talk_frequency_adjust(self) -> float`**：
    - 返回 `self._talk_frequency_adjust`
  - 注意：`adjust_talk_frequency` 方法已存在于 `runtime.py:541`，无需新增
  - **验收标准**：`runtime.append_context_message(context_message)` 后 `runtime._chat_history[-1]` 与传入的 `message` 对象相同；`runtime.get_talk_frequency_adjust()` 返回值与直接读取 `runtime._talk_frequency_adjust` 一致
  - **文件锁**：`src/maisaka/runtime.py`

### 1.5 启动流程注册 MessageIngestionPort + main.py 消费方迁移

- [ ] 在 `src/main.py` 的 `MainSystem` 中新增启动步骤 + 迁移 chat_bot 消费方（合并原 2.1，避免跨批次文件锁冲突）：
  - **启动注册**：
    - 在 `CORE_SERVICES` 阶段，`_init_llm_service_port`（order=7）之后新增 `_init_message_ingestion_port`（order=8），后续步骤顺延
    - 新增 `_init_message_ingestion_port` 静态方法：
      ```python
      @staticmethod
      async def _init_message_ingestion_port() -> None:
          from src.chat.message_receive.bot import chat_bot
          from src.core.adapters.message_ingestion_port import ChatBotMessageIngestionPort, set_message_ingestion_port
          set_message_ingestion_port(ChatBotMessageIngestionPort(chat_bot))
      ```
  - **消费方迁移**（原 2.1）：
    - 在 `_register_message_handlers` 方法中：
      - 新增 `from src.core.adapters.message_ingestion_port import get_message_ingestion_port`
      - 将 `self.app.register_message_handler(chat_bot.message_process)` 改为 `self.app.register_message_handler(get_message_ingestion_port().message_process)`
      - 保留 `from src.chat.message_receive.bot import chat_bot` 导入用于 `chat_bot.echo_message_process`（main.py 已有 TID251 豁免）
      - 注意：`message_process` 是绑定方法，`get_message_ingestion_port().message_process` 返回的也是绑定方法，可作为回调注册
  - **验收标准**：启动后 `get_message_ingestion_port()` 可正常返回实例；`chat_bot.message_process` 回调改为通过注册点；`echo_message_process` 保留原样；`rg "chat_bot.message_process" src/main.py` 无结果
  - **文件锁**：`src/main.py`（CC 统一处理，避免跨批次冲突）

### 1.6 ruff banned-api 守卫 + per-file-ignores 适配

- [ ] 在 `pyproject.toml` 中新增 banned-api 条目和 per-file-ignores 适配：
  - **banned-api 新增**：
    ```toml
    "src.chat.message_receive.bot.chat_bot" = {msg = "禁止直接导入 chat_bot 全局单例，请使用 MessageIngestionPort Protocol 接口（get_message_ingestion_port()）"}
    ```
  - **per-file-ignores 确认**：
    - `src/core/adapters/*` 已有 TID251 豁免（无需新增）
    - `src/main.py` 已有 TID251 豁免（无需新增）
    - `src/chat/message_receive/bot.py` 需新增 TID251 豁免：`"src/chat/message_receive/bot.py" = ["TID251"]`（定义文件本身允许导入）
  - **验收标准**：在消费方文件（如 `integration.py`）中添加 `from src.chat.message_receive.bot import chat_bot` → ruff check 报 TID251 错误；适配器层 `message_ingestion_port.py` 和 `main.py` 不触发 TID251；`bot.py` 自身不触发 TID251
  - **文件锁**：`pyproject.toml`

---

## 2. H4 消费方迁移（chat_bot 直接导入消除）

**负责人**：Codex（机械性替换，模式统一）

**前置条件**：批次 1 完成（MessageIngestionPort Protocol + 适配器 + 注册点 + 启动注册可用）

### 2.1 integration.py 消费方迁移（1 处）

- [ ] 迁移 `src/plugin_runtime/integration.py` 中 `chat_bot` 直接导入（L140-142）：
  - 删除 `from src.chat.message_receive.bot import chat_bot`
  - 新增 `from src.core.adapters.message_ingestion_port import get_message_ingestion_port`
  - 将 `await chat_bot.receive_message(session_message)` 改为 `await get_message_ingestion_port().receive_message(session_message)`
  - **验收标准**：`rg "from src.chat.message_receive.bot import chat_bot" src/plugin_runtime/integration.py` 无结果；插件消息转发功能不变
  - **文件锁**：`src/plugin_runtime/integration.py`

### 2.2 message_gateway.py 消费方迁移（1 处）

- [ ] 迁移 `src/plugin_runtime/host/message_gateway.py` 中 `chat_bot` 直接导入（L68-70）：
  - 删除 `from src.chat.message_receive.bot import chat_bot`
  - 新增 `from src.core.adapters.message_ingestion_port import get_message_ingestion_port`
  - 将 `await chat_bot.receive_message(session_message)` 改为 `await get_message_ingestion_port().receive_message(session_message)`
  - **验收标准**：`rg "from src.chat.message_receive.bot import chat_bot" src/plugin_runtime/host/message_gateway.py` 无结果；消息网关转发功能不变
  - **文件锁**：`src/plugin_runtime/host/message_gateway.py`

### 2.3 service.py 消费方迁移（1 处）

- [ ] 迁移 `src/webui/routers/chat/service.py` 中 `chat_bot` 直接导入（L13 模块级 + L1255 调用）：
  - 删除模块级 `from src.chat.message_receive.bot import chat_bot`
  - 新增模块级 `from src.core.adapters.message_ingestion_port import get_message_ingestion_port`
  - 将 L1255 `await chat_bot.message_process(message_data)` 改为 `await get_message_ingestion_port().message_process(message_data)`
  - **验收标准**：`rg "from src.chat.message_receive.bot import chat_bot" src/webui/routers/chat/service.py` 无结果；WebUI 聊天消息处理功能不变
  - **文件锁**：`src/webui/routers/chat/service.py`

---

## 3. H5 消费方迁移（heartflow_manager 私有属性访问消除）

**负责人**：Codex（机械性替换，通过 ChatRuntimeRegistry + ChatRuntime Protocol 替代直接导入）

**前置条件**：批次 1 完成（ChatRuntime Protocol 扩展 + MaisakaRuntime 新增方法可用）

### 3.1 capabilities/core.py 消费方迁移（2 处 heartflow_manager 导入 + 1 处 _chat_history 访问）

- [ ] 迁移 `src/plugin_runtime/capabilities/core.py` 中 2 处 `heartflow_manager` 直接导入和 1 处 `_chat_history` 私有属性访问：
  - **第 1 处**（`_cap_maisaka_context_append` 方法，L186-214）：
    - 删除 `from src.chat.heart_flow.heartflow_manager import heartflow_manager`
    - 新增 `from src.core.runtime_port_registry import get_chat_runtime_registry`
    - 将 `runtime = await heartflow_manager.get_or_create_heartflow_chat(stream_id)` 改为 `registry = get_chat_runtime_registry(); runtime = await registry.get_or_create_runtime(stream_id)`
    - 将 `runtime._chat_history.append(context_message)` 改为 `index = runtime.append_context_message(context_message, source_kind=source_kind)`
    - 将 `"index": len(runtime._chat_history) - 1` 改为 `"index": index`（直接使用 `append_context_message` 返回值）
  - **第 2 处**（`_cap_maisaka_proactive_trigger` 方法，L232-249）：
    - 删除 `from src.chat.heart_flow.heartflow_manager import heartflow_manager`
    - 新增 `from src.core.runtime_port_registry import get_chat_runtime_registry`（如已导入则不重复）
    - 将 `runtime = await heartflow_manager.get_or_create_heartflow_chat(stream_id)` 改为 `registry = get_chat_runtime_registry(); runtime = await registry.get_or_create_runtime(stream_id)`
    - `runtime.enqueue_proactive_task(...)` 调用不变（已是 Protocol 方法）
  - **验收标准**：`rg "heartflow_manager" src/plugin_runtime/capabilities/core.py` 无结果；`rg "_chat_history" src/plugin_runtime/capabilities/core.py` 无结果；插件上下文注入和主动对话触发功能不变
  - **文件锁**：`src/plugin_runtime/capabilities/core.py`

### 3.2 capabilities/data.py 消费方迁移（2 处 heartflow_manager 导入 + 1 处 _talk_frequency_adjust 访问）

- [ ] 迁移 `src/plugin_runtime/capabilities/data.py` 中 2 处 `heartflow_manager` 直接导入和 1 处 `_talk_frequency_adjust` 私有属性访问：
  - **第 1 处**（`_get_frequency_adjust_value` 静态方法，L803-807）：
    - 删除 `from src.chat.heart_flow.heartflow_manager import heartflow_manager`
    - 新增 `from src.core.runtime_port_registry import get_chat_runtime_registry`
    - 将 `heartflow_chat = heartflow_manager.heartflow_chat_list.get(chat_id)` + `return 1.0 if heartflow_chat is None else heartflow_chat._talk_frequency_adjust` 改为：
      ```python
      registry = get_chat_runtime_registry()
      runtime = await registry.get_runtime(chat_id) if registry else None
      return 1.0 if runtime is None else runtime.get_talk_frequency_adjust()
      ```
    - 注意：此方法是 `@staticmethod`，需改为 `async staticmethod` 或调整为普通方法。如果调用方已是 `async`，直接改为 `async` 即可。需检查调用方 `_cap_frequency_get_current_talk_value`（L809）和 `_cap_frequency_get_adjust`（L838）是否已是 async——确认两者都是 `async def`，因此 `_get_frequency_adjust_value` 需改为 `async` 并在调用处加 `await`。
  - **第 2 处**（`_cap_frequency_set_adjust` 方法，L823-836）：
    - 删除 `from src.chat.heart_flow.heartflow_manager import heartflow_manager`
    - 新增 `from src.core.runtime_port_registry import get_chat_runtime_registry`（如已导入则不重复）
    - 将 `heartflow_manager.adjust_talk_frequency(chat_id, float(value))` 改为：
      ```python
      registry = get_chat_runtime_registry()
      if registry:
          runtime = await registry.get_runtime(chat_id)
          if runtime:
              runtime.adjust_talk_frequency(float(value))
      ```
  - **验收标准**：`rg "heartflow_manager" src/plugin_runtime/capabilities/data.py` 无结果；`rg "_talk_frequency_adjust" src/plugin_runtime/capabilities/data.py` 无结果；频率查询和调整功能不变
  - **文件锁**：`src/plugin_runtime/capabilities/data.py`

---

## 4. 验证与清理（ruff 全量验证 + 适配器 __init__ 更新 + hook_catalog 确认）

**负责人**：CX（机械性验证+清理，按检查清单执行即可）

**前置条件**：批次 2-3 完成（所有消费方已迁移）

### 4.1 适配器 __init__.py 导出更新

- [ ] 在 `src/core/adapters/__init__.py` 中新增 `MessageIngestionPort` 相关导出：
  - 新增 `from src.core.adapters.message_ingestion_port import get_message_ingestion_port, reset_message_ingestion_port  # noqa: F401`
  - 在 `__all__` 列表中新增 `"get_message_ingestion_port"` 和 `"reset_message_ingestion_port"`
  - **⚠️ 历史重犯提醒**：SSD-6 和 SSD-7 各忘更新 `__all__` 一次，务必自检！
  - **验收标准**：`from src.core.adapters import get_message_ingestion_port` 可正常导入；`__all__` 列表包含新增项
  - **文件锁**：`src/core/adapters/__init__.py`

### 4.2 hook_catalog.py 导入路径确认

- [ ] 确认 `src/plugin_runtime/hook_catalog.py` 中 `register_chat_hook_specs` 的导入路径：
  - 当前导入：`from src.chat.message_receive.bot import register_chat_hook_specs`（L22）
  - `register_chat_hook_specs` 是纯函数，不依赖 `chat_bot` 实例，仅注册 Hook 规格
  - `hook_catalog.py` 已有 TID251 豁免（`pyproject.toml:L113`）
  - **决策**：保留现有导入路径不变（函数级导入，非实例导入，架构上可接受）。在导入行添加注释说明原因：
    ```python
    # 纯函数导入，不依赖 chat_bot 实例；TID251 已豁免
    from src.chat.message_receive.bot import register_chat_hook_specs
    ```
  - **验收标准**：`hook_catalog.py` 导入路径不变；添加了说明性注释；ruff check 不报错（已有豁免）
  - **文件锁**：`src/plugin_runtime/hook_catalog.py`

### 4.3 全量验证

- [ ] 执行全量验证，确认迁移完成：
  - 运行 `rg "from src.chat.message_receive.bot import chat_bot" src/` → 仅剩 `src/main.py`（用于 `echo_message_process`，有 TID251 豁免）、`src/core/adapters/message_ingestion_port.py`（适配器层，有 TID251 豁免）、`src/chat/message_receive/bot.py`（定义文件自身）
  - 运行 `rg "heartflow_manager" src/plugin_runtime/` → 零结果
  - 运行 `rg "_chat_history" src/plugin_runtime/` → 零结果
  - 运行 `rg "_talk_frequency_adjust" src/plugin_runtime/` → 零结果
  - 运行 `ruff check src/` → 零 TID251 违规（除已豁免文件外）
  - 确认 `MaisakaRuntime` 满足扩展后的 `ChatRuntime` Protocol（`isinstance(runtime, ChatRuntime)` 返回 True）
  - 确认 `ChatBotMessageIngestionPort` 满足 `MessageIngestionPort` Protocol（`isinstance(adapter, MessageIngestionPort)` 返回 True）
  - **验收标准**：5 条验证命令结果符合预期；Protocol 鸭子类型检查通过
  - **文件锁**：无（验证任务，不修改文件）

---

## 附录：不在范围内的事项

1. **ChatBot 类内部重构**：不修改 `ChatBot` 的消息处理逻辑、Hook 触发逻辑或命令分发逻辑
2. **HeartflowManager 类内部重构**：不修改 `HeartflowManager` 的运行时生命周期管理逻辑
3. **MaisakaRuntime 核心对话循环重构**：不修改核心对话循环、回复生成等逻辑
4. **MaisakaRuntime._chat_history 私有属性重命名**：`_chat_history` 作为内部实现细节保留，仅通过 `append_context_message()` Protocol 方法暴露公共能力
5. **MaisakaRuntime 其他私有属性暴露**：除 `append_context_message`/`get_talk_frequency_adjust`/`adjust_talk_frequency` 外，不暴露其他私有属性
6. **register_chat_hook_specs 函数迁移**：纯函数导入，保留在 `bot.py` 中，`hook_catalog.py` 已有 TID251 豁免
7. **WebUI service.py 的其他直接导入**：`service.py` 中还有 `is_bot_self`、`global_config` 等直接导入，这些属于其他 SSD 范围
8. **MaisakaRuntime 内部的 _chat_history 访问**：Maisaka 内部模块（builtin_tool、focus_mixin 等）对 `_chat_history` 的直接访问不在本期范围，这些是内部实现而非跨层访问
9. **ChatRuntimeRegistry.get_or_create_runtime 新增**：当前 `ChatRuntimeRegistry` 已有 `get_runtime()` 和 `get_or_create_runtime()` 方法，无需新增