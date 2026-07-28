# Phoenix-2：MCP 组件模型 — 编码任务规划

## 1. SDK v4 PluginContext 运行时补全

补全 PluginContext 及其子对象的运行时实现，使插件开发者可通过 `self.ctx` 调用日志、事件推送、卡片推送等能力。SendContext/StorageContext/get_session_info 保留 scope 校验 + 占位返回，RPC 通道由 Phoenix-4 实现。

### 1.1 LoggerContext 桥接到 get_logger

- [ ] 修改 `src/plugin_runtime_v2/sdk/context.py` 中 `LoggerContext.__init__`，导入 `src.common.logger.get_logger`，创建 `self._logger = get_logger(f"plugin.{plugin_id}")` 实例
- [ ] 补全 `LoggerContext.debug/info/warning/error` 四个方法，委托调用 `self._logger.debug/info/warning/error`
- [ ] 移除 `LoggerContext.__init__` 中的 `self._prefix` 占位逻辑

**预估**：~15 行变更 | **负责人**：Codex（机械补全，逻辑明确）

### 1.2 PluginContext.emit_event 实际推送

- [ ] 修改 `PluginContext.__init__` 签名，新增 `runner_endpoint: RunnerEndpoint` 和 `homecard_registry: dict[str, dict[str, Any]]` 参数，存储为 `self._runner` 和 `self._homecard_registry`
- [ ] 修改 `SendContext.__init__` 签名，新增 `runner_endpoint: RunnerEndpoint` 参数，存储为 `self._runner`
- [ ] 修改 `StorageContext.__init__` 签名，新增 `runner_endpoint: RunnerEndpoint` 和 `plugin_id: str` 参数，存储为 `self._runner` 和 `self._plugin_id`
- [ ] 实现 `PluginContext.emit_event(name, payload)`：校验 Runner 状态（`self._runner.is_ready`），不 ready 时抛出 `ConnectionError("Runner 未连接")`；ready 时调用 `self._runner.emit_event(name, payload)`
- [ ] 添加 `TYPE_CHECKING` 导入 `RunnerEndpoint`，避免循环导入

**预估**：~30 行变更 | **负责人**：Codex（参数传递 + 条件判断）

### 1.3 PluginContext.emit_card 自动构造 HomeCard 数据

- [ ] 实现 `PluginContext.emit_card(name, data)`：从 `self._homecard_registry` 查找 `name` 对应的 `card_metadata`
- [ ] 若 `card_metadata` 不存在，记录 WARNING 日志（`self._logger.warning`），仍继续推送
- [ ] 构造 HomeCard 数据结构：`{"name": name, "title": card_metadata.get("title", ""), "width": card_metadata.get("width", "medium"), "data": data}`
- [ ] 调用 `self.emit_event(name, homecard_payload)` 推送

**预估**：~20 行变更 | **负责人**：Codex（数据构造 + 委托调用）

### 1.4 PluginContext.get_session_info 占位实现

- [ ] 在 `PluginContext` 中新增 `async def get_session_info(self, session_id: str) -> dict[str, Any]` 方法
- [ ] 校验 `session:read:detail` scope，未授权抛出 `ScopeDeniedError`
- [ ] 方法体标注 `# TODO: Phoenix-4 实现 RPC 通道`，返回占位 `{"session_id": session_id, "session_name": "", "platform": "", "is_group_session": False}`

**预估**：~15 行变更 | **负责人**：Codex（模式同 SendContext/StorageContext）

### 1.5 SendContext/StorageContext 占位返回标注

- [ ] 修改 `SendContext` 的 5 个方法（text/image/emoji/forward/hybrid）方法体注释，将"Phoenix-1 实现实际发送"改为"Phoenix-4 实现 RPC 通道"，方法体不变（保留 scope 校验 + 占位返回）
- [ ] 修改 `StorageContext` 的 3 个方法（get/set/delete）方法体注释，同理改为"Phoenix-4 实现 RPC 通道"
- [ ] 确认所有占位方法体标注 `# TODO: Phoenix-4 实现 RPC 通道`

**预估**：~10 行变更 | **负责人**：Codex（注释修改）

### 1.6 @HomeCard width 校验

- [ ] 修改 `src/plugin_runtime_v2/sdk/decorators.py` 中 `HomeCard` 装饰器，在 `decorator` 函数内校验 `width` 参数是否为 `"small"/"medium"/"large"/"wide"/"full"` 之一
- [ ] 不合法时抛出 `ValueError(f"HomeCard width 必须为 small/medium/large/wide/full 之一，得到: {width}")`

**预估**：~5 行变更 | **负责人**：Codex（单条件校验）

### 1.7 单元测试：PluginContext 运行时

- [ ] 编写 `tests/plugin_runtime_v2/sdk/test_context_runtime.py`
- [ ] 测试 LoggerContext 桥接：验证 `info("test")` 调用后 logger 实例被调用
- [ ] 测试 emit_event：mock RunnerEndpoint，验证 `emit_event("evt", {"k": "v"})` 调用了 `runner.emit_event`
- [ ] 测试 emit_event Runner 未连接：验证抛出 `ConnectionError`
- [ ] 测试 emit_card：验证构造的 HomeCard 数据结构正确（含 name/title/width/data）
- [ ] 测试 emit_card 未注册名称：验证仍推送 Event 但记录 WARNING
- [ ] 测试 get_session_info scope 校验：未授权抛出 `ScopeDeniedError`
- [ ] 测试 @HomeCard width 校验：非法值抛出 `ValueError`

**预估**：~120 行 | **负责人**：Codex（测试模式清晰）

---

## 2. Runner 端 Tool 执行路由

实现 ToolRouter，替换 `_PluginRunnerServicer.InvokeTool` 的 NOT_IMPLEMENTED 占位，根据 tool_name 查找 @Tool/@Command 装饰器注册的处理函数并执行。

### 2.1 实现 ToolRouter

- [ ] 新建 `src/plugin_runtime_v2/runner/tool_router.py`
- [ ] 定义 `ToolRouter` 类，`_handlers: dict[str, tuple[MaiBotPlugin, Callable, ToolDeclaration | None]]`
- [ ] 实现 `register(tool_name, plugin, handler, declaration=None)`：注册处理函数
- [ ] 实现 `unregister(tool_name)`：注销处理函数
- [ ] 实现 `has(tool_name) -> bool`：判断 Tool 是否已注册
- [ ] 实现 `async execute(tool_name, args, timeout_ms=30000) -> InvokeToolResponse`：
  - 查找 tool_name，不存在返回 `success=false, error="TOOL_NOT_FOUND"`
  - 参数校验（使用 `declaration.parameters_schema`，jsonschema 校验），失败返回 `PARAMETER_VALIDATION_FAILED: {detail}`
  - 执行 `handler(plugin, args)`，使用 `asyncio.wait_for` 超时控制
  - 超时返回 `TIMEOUT`，异常返回 `EXECUTION_ERROR: {exc.__class__.__name__}: {detail}`
  - 成功返回 `success=true, result=json.dumps(result)`
- [ ] 使用 `src.common.logger.get_logger("plugin_runtime_v2.runner.tool_router")` 记录日志
- [ ] 处理函数可能是同步或异步：使用 `inspect.iscoroutinefunction` 判断，异步则 await，同步则用 `asyncio.to_thread(handler, plugin, args)` 包装避免阻塞事件循环

**预估**：~100 行 | **负责人**：CC（涉及超时控制、参数校验、异常映射等复杂逻辑）

### 2.2 参数校验实现

- [ ] 在 `ToolRouter.execute` 中，若 `declaration` 不为 None 且 `declaration.parameters_schema` 不为 None，使用 `jsonschema.validate(args, schema)` 校验
- [ ] 导入 `jsonschema`（pyproject.toml 中当前无此依赖，需添加 `jsonschema>=4.0`）
- [ ] 校验失败捕获 `jsonschema.ValidationError`，返回 `PARAMETER_VALIDATION_FAILED: {exc.message}`
- [ ] `declaration` 为 None 时跳过参数校验

**预估**：~15 行（含在 2.1 中） | **负责人**：CC（与 2.1 合并实现）

### 2.3 单元测试：ToolRouter

- [ ] 编写 `tests/plugin_runtime_v2/runner/test_tool_router.py`
- [ ] 测试 register/unregister/has 基本流程
- [ ] 测试 execute 成功：返回 `success=true, result=JSON`
- [ ] 测试 TOOL_NOT_FOUND：未注册 tool_name
- [ ] 测试 TIMEOUT：处理函数超时
- [ ] 测试 EXECUTION_ERROR：处理函数抛出异常
- [ ] 测试 PARAMETER_VALIDATION_FAILED：args 不符合 parameters_schema
- [ ] 测试同步和异步处理函数均可执行

**预估**：~100 行 | **负责人**：Codex（测试模式清晰，依赖 2.1 完成后编写）

---

## 3. Runner 端插件加载与装饰器收集

实现 PluginLoader，扫描 MaiBotPlugin 子类，收集装饰器声明，管理插件生命周期（on_load/on_unload），注入 PluginContext。

### 3.1 实现 PluginLoader

- [ ] 新建 `src/plugin_runtime_v2/runner/plugin_loader.py`
- [ ] 定义 `PluginLoader` 类，`__init__(self, runner_endpoint: RunnerEndpoint)`
- [ ] 实现 `async load(self, plugin_class: type[MaiBotPlugin]) -> MaiBotPlugin`：
  - 检查 `_plugin_loaded` 标记，若已加载则跳过（避免 Runner 重连时重复加载）
  - 实例化插件
  - 调用 `collect_declarations` 收集声明
  - 构建 `homecard_registry`：从 EventDeclaration 中提取含 `card_metadata` 的声明
  - 注入 PluginContext：`plugin.ctx = PluginContext(plugin.plugin_id, set(plugin.scopes), runner_endpoint, homecard_registry)`
  - 调用 `plugin.on_load()`，使用 `inspect.iscoroutinefunction` 判断是否 await
  - on_load 异常时记录 ERROR 日志并上浮
- [ ] 实现 `collect_declarations(self, plugin: MaiBotPlugin) -> tuple[list[ToolDeclaration], list[EventDeclaration]]`：
  - 使用 `inspect.getmembers(plugin, predicate=inspect.ismethod)` 扫描方法
  - 检查每个方法是否有 `_mcp_tool` 或 `_mcp_event` 属性
  - 收集为 SDK 层 ToolDeclaration/EventDeclaration 列表
- [ ] 实现 `async unload(self, plugin: MaiBotPlugin) -> None`：
  - 调用 `plugin.on_unload()`，使用 `inspect.iscoroutinefunction` 判断是否 await
- [ ] 使用 `src.common.logger.get_logger("plugin_runtime_v2.runner.plugin_loader")` 记录日志

**预估**：~80 行 | **负责人**：CC（涉及生命周期管理和 inspect 扫描，需仔细处理边界情况）

### 3.2 SDK 层声明 → proto 层声明转换

- [ ] 在 `PluginLoader` 中实现 `_to_proto_tool_declarations(tool_decls: list[ToolDeclaration]) -> list[proto.ToolDeclaration]`：
  - name → name
  - description → description
  - parameters_schema → JSON 字符串（json.dumps）；如果 `pattern` 不为 None，将其存入 parameters_schema 的 `x-maibot-command-pattern` 扩展字段
  - output_schema → JSON 字符串，None → `"{}"`
- [ ] 在 `PluginLoader` 中实现 `_to_proto_event_declarations(event_decls: list[EventDeclaration]) -> list[proto.EventDeclaration]`：
  - name → name
  - description → description
  - event_schema → JSON 字符串，None → `"{}"`
  - card_metadata → 存入 event_schema 的 `x-maibot-card-metadata` 扩展字段

**预估**：~40 行 | **负责人**：CC（与 3.1 合并实现）

### 3.3 单元测试：PluginLoader

- [ ] 编写 `tests/plugin_runtime_v2/runner/test_plugin_loader.py`
- [ ] 创建测试插件类（含 @Tool/@Event/@Command/@HomeCard）
- [ ] 测试 load：实例化 → 收集声明 → 注入 PluginContext → 调用 on_load
- [ ] 测试 collect_declarations：验证收集到正确数量和内容的声明
- [ ] 测试 _to_proto_tool_declarations：验证 pattern 存入 x-maibot-command-pattern
- [ ] 测试 _to_proto_event_declarations：验证 card_metadata 存入 x-maibot-card-metadata
- [ ] 测试 on_load 异常：验证异常上浮
- [ ] 测试 unload：验证 on_unload 被调用

**预估**：~120 行 | **负责人**：Codex（依赖 3.1 完成后编写）

---

## 4. Host 端 ToolProvider 桥接

实现 MCPToolProvider，将远程插件的 ToolDeclaration 映射为 ToolSpec 注册到 ToolRegistry，将 ToolInvocation 转发为 InvokeTool RPC 调用。

### 4.1 实现 MCPToolProvider

- [ ] 新建 `src/plugin_runtime_v2/mcp/tool_provider.py`
- [ ] 定义 `MCPToolProvider` 类：
  - `provider_name: str`（等于 plugin_id）
  - `provider_type: str`（固定 `"mcp_remote"`）
  - `__init__(self, plugin_id, runner_id, tool_declarations, runner_listen_address)`
- [ ] 在 `__init__` 中创建 gRPC channel 和 stub：`self._channel = grpc.aio.insecure_channel(runner_listen_address)` + `self._stub = PluginRunnerStub(self._channel)`，避免每次 invoke 创建新连接
- [ ] 实现 `__init__` 中的 ToolDeclaration → ToolSpec 映射：
  - 遍历 `tool_declarations`（protobuf 对象），对每个执行映射
  - `parameters_schema`：`json.loads` 解析 JSON 字符串为 dict；剥离 `x-maibot-command-pattern` 扩展字段，剥离值赋值给 `metadata["pattern"]`
  - `json.loads` 失败时记录 WARNING 日志（含 tool_name 和原始 schema），跳过该 Tool
  - `output_schema`：`json.loads` 解析，失败时设为 None
  - 构造 `ToolSpec` 列表缓存到 `self._tool_specs`
- [ ] 实现 `async list_tools(context=None) -> list[ToolSpec]`：返回 `self._tool_specs`（不重新构造）
- [ ] 实现 `async invoke(invocation, context=None) -> ToolExecutionResult`：
  - 使用 `self._stub.InvokeTool(request, timeout=...)` 调用 RPC
  - RPC 超时（`grpc.aio.AioRpcError` 且 `code() == DEADLINE_EXCEEDED`）→ `success=false, error="Tool {name} 调用超时"`
  - Runner 不可用 → `success=false, error="Runner {id} 不可用"`
  - 其他 RPC 异常 → `success=false, error="{exc.__class__.__name__}: {detail}"`
  - 成功 → 映射 `InvokeToolResponse` 为 `ToolExecutionResult`（success→success, result→content, error→error_message）
- [ ] 实现 `async close() -> None`：关闭 gRPC channel（`await self._channel.close()`）
- [ ] 使用 `src.common.logger.get_logger("plugin_runtime_v2.mcp.tool_provider")` 记录日志

**预估**：~120 行 | **负责人**：CC（涉及 Protocol 实现、gRPC 调用、异常映射，是核心链路关键模块）

### 4.2 单元测试：MCPToolProvider

- [ ] 编写 `tests/plugin_runtime_v2/mcp/test_tool_provider.py`
- [ ] 测试 ToolDeclaration → ToolSpec 映射：验证 name/description/parameters_schema/provider_name/provider_type 正确
- [ ] 测试 x-maibot-command-pattern 剥离：验证 pattern 存入 metadata["pattern"]，parameters_schema 中不含该字段
- [ ] 测试 parameters_schema 解析失败：验证跳过该 Tool，记录 WARNING
- [ ] 测试 list_tools 返回缓存列表
- [ ] 测试 invoke 成功：mock gRPC stub，验证 ToolExecutionResult 映射
- [ ] 测试 invoke RPC 超时：验证返回 success=false
- [ ] 测试 invoke Runner 不可用：验证返回 success=false

**预估**：~120 行 | **负责人**：Codex（依赖 4.1 完成后编写）

---

## 5. Host 端 Event 分发

实现 EventDispatcher，将 Runner 推送的 Event 分发到核心事件系统（ThinkingOrgan 主动思考、WebUI HomeCard 等）。

### 5.1 实现 EventDispatcher

- [ ] 新建 `src/plugin_runtime_v2/mcp/event_dispatcher.py`
- [ ] 定义 `EventDispatcher` 类：
  - `__init__(self, message_port: MessagePortV2, session_repo: SessionRepository, person_info_port: PersonInfoPort)`
- [ ] 实现 `async dispatch(self, event_name, payload, plugin_id, event_declaration) -> None`：
  - `event_declaration` 为 None 时记录 WARNING 日志并返回
  - Event 含 `card_metadata`（`event_declaration.card_metadata is not None`）→ 转发 HomeCard 数据到 WebUI（当前阶段记录 INFO 日志，WebUI 对接由 Phoenix-3/4 实现）
  - Event 需要触发思考（event_name 在预定义列表中，如 `"timer"`, `"environment_change"`）→ 构造 ThinkContext 调用 ThinkingOrgan.think_proactive()（当前阶段记录 INFO 日志，ThinkingOrgan 对接由后续实现）
  - 其他 Event → 记录 INFO 日志
  - 分发失败仅记录 WARNING 日志，不抛出异常（try-except 包裹每个分发路径）
- [ ] 使用 `src.common.logger.get_logger("plugin_runtime_v2.mcp.event_dispatcher")` 记录日志

**预估**：~60 行 | **负责人**：Codex（分发逻辑为简单条件分支 + 日志，Phoenix-2 阶段不对接实际 ThinkingOrgan/WebUI）

### 5.2 单元测试：EventDispatcher

- [ ] 编写 `tests/plugin_runtime_v2/mcp/test_event_dispatcher.py`
- [ ] 测试 dispatch 含 card_metadata 的 Event：验证日志记录 HomeCard 分发
- [ ] 测试 dispatch 触发思考的 Event：验证日志记录 think_proactive 分发
- [ ] 测试 dispatch 普通 Event：验证日志记录
- [ ] 测试 dispatch event_declaration 为 None：验证 WARNING 日志
- [ ] 测试 dispatch 分发失败隔离：验证单个 Event 异常不影响后续

**预估**：~80 行 | **负责人**：Codex（依赖 5.1 完成后编写）

---

## 6. Host 端 MCP 协调与 @Command 兼容

实现 MCPHostBridge，协调 MCPToolProvider 注册/注销和 EventDispatcher 分发，实现 @Command 群消息上下文自动注入。

### 6.1 实现 MCPHostBridge

- [ ] 新建 `src/plugin_runtime_v2/mcp/host_bridge.py`
- [ ] 定义 `MCPHostBridge` 类：
  - `__init__(self, tool_registry: ToolRegistry, event_dispatcher: EventDispatcher, person_info_port: PersonInfoPort)`
  - 内部状态：`_providers: dict[str, MCPToolProvider]`（key=plugin_id）、`_event_declarations: dict[str, EventDeclaration]`（key=event_name）
- [ ] 实现 `on_runner_registered(self, runner_id, plugin_id, tools, events, runner_listen_address)`：
  - 处理重连场景：如果 `plugin_id` 已在 `_providers` 中，先注销旧的（`tool_registry.unregister_provider` + 关闭旧 provider）
  - 创建 `MCPToolProvider`（需创建 gRPC stub 连接到 `runner_listen_address`）
  - 注册到 `tool_registry.register_provider(provider)`
  - 从 `events` 列表构建 `_event_declarations` 映射（event_name → EventDeclaration）
  - 记录 INFO 日志
- [ ] 实现 `on_runner_disconnected(self, runner_id, plugin_id)`：
  - 从 `_providers` 中查找并注销 `MCPToolProvider`
  - 调用 `tool_registry.unregister_provider(plugin_id)`
  - 清理 `_event_declarations` 中该 plugin 的条目
  - 记录 INFO 日志
- [ ] 实现 `async on_event_received(self, runner_id, plugin_id, event_name, payload)`：
  - 预查找 `_event_declarations[event_name]`
  - 调用 `event_dispatcher.dispatch(event_name, payload, plugin_id, event_declaration)`
- [ ] 使用 `src.common.logger.get_logger("plugin_runtime_v2.mcp.host_bridge")` 记录日志

**预估**：~100 行 | **负责人**：CC（涉及 Runner 生命周期管理、重连处理、gRPC stub 创建，是核心协调模块）

### 6.2 实现 @Command 上下文注入

- [ ] 在 `MCPHostBridge` 中实现 `_inject_command_context(self, invocation: ToolInvocation, context: ToolExecutionContext | None) -> None`：
  - 从 `self._providers[invocation.provider_name]` 获取 MCPToolProvider（需调整：从 ToolSpec.metadata["pattern"] 判断）
  - 实际方案：从 `tool_registry` 查找 ToolSpec，检查 `metadata` 是否含 `"pattern"` 键
  - 若含 pattern（即 @Command），从 `context` 提取上下文参数：
    - `session_id ← invocation.session_id`
    - `sender_id ← context.user_id`（context 为 None 或缺字段时注入空字符串）
    - `sender_name ← self._person_info_port.query(sender_id).person_name`（查询失败时为空字符串）
    - `is_group_chat ← context.is_group_chat`（缺字段时为 False）
  - 将上下文参数注入 `invocation.arguments`，**不覆盖已有参数**
- [ ] 此方法在 MCPToolProvider.invoke 之前调用（由回调注入层保证调用顺序）

**预估**：~40 行 | **负责人**：CC（涉及 ToolExecutionContext 解析、PersonInfoPort 调用、参数注入逻辑）

### 6.3 单元测试：MCPHostBridge

- [ ] 编写 `tests/plugin_runtime_v2/mcp/test_host_bridge.py`
- [ ] 测试 on_runner_registered：验证 MCPToolProvider 创建并注册到 ToolRegistry
- [ ] 测试 on_runner_registered 重连场景：验证先注销旧 provider 再注册新
- [ ] 测试 on_runner_disconnected：验证 provider 注销
- [ ] 测试 on_event_received：验证 EventDispatcher.dispatch 被调用
- [ ] 测试 on_event_received 未注册 Event：验证 event_declaration 为 None
- [ ] 测试 _inject_command_context：验证上下文参数注入（session_id/sender_id/sender_name/is_group_chat）
- [ ] 测试 _inject_command_context 不覆盖已有参数

**预估**：~120 行 | **负责人**：Codex（依赖 6.1/6.2 完成后编写）

---

## 7. Host/Runner 端回调注入

扩展 Phoenix-1 的 Host/Runner 端代码，通过注入回调将 MCPHostBridge、ToolRouter、PluginLoader 接入现有流程。不修改核心逻辑，只在关键点注入回调。

### 7.1 Host 端 _PluginHostServicer 扩展

- [ ] 修改 `src/plugin_runtime_v2/host/servicer.py` 中 `_PluginHostServicer.__init__`，新增 `host_bridge: MCPHostBridge | None = None` 参数
- [ ] 在 `RegisterComponents` 成功后（`conn.transition(ConnectionState.READY)` 之后），调用 `self._host_bridge.on_runner_registered(runner_id, request.plugin_id, list(request.tools), list(request.events), conn._runner_listen_address)`（需从 RunnerConnection 获取 runner_listen_address）
- [ ] 在 `_cleanup_connection` 中，调用 `self._host_bridge.on_runner_disconnected(runner_id, conn.plugin_id)`（在 `self._registry.unregister` 之前）
- [ ] 在 Connect 双向流 `_recv_loop` 中收到 EventPayload 后，解析 payload JSON，调用 `await self._host_bridge.on_event_received(runner_id, conn.plugin_id, event.event_name, payload_dict)`（在返回 EventAck 之前）
- [ ] Event 分发失败不得影响 EventAck 返回（try-except 包裹 on_event_received 调用）

**预估**：~30 行变更 | **负责人**：CC（涉及 Servicer 核心流程扩展，需确保不影响现有逻辑）

### 7.2 Host 端 HostEndpoint 扩展

- [ ] 修改 `src/plugin_runtime_v2/host/endpoint.py` 中 `HostEndpoint.__init__`，新增 `host_bridge: MCPHostBridge | None = None` 参数
- [ ] 将 `host_bridge` 传递给 `_PluginHostServicer`
- [ ] HostBridge 构造需传入 `tool_registry`、`event_dispatcher`、`person_info_port`——这些依赖在 HostEndpoint 层面获取或创建

**预估**：~15 行变更 | **负责人**：CC（与 7.1 配合）

### 7.3 Runner 端 _PluginRunnerServicer 扩展

- [ ] 修改 `src/plugin_runtime_v2/runner/servicer.py` 中 `_PluginRunnerServicer.__init__`，新增 `tool_router: ToolRouter | None = None` 参数
- [ ] 替换 `InvokeTool` 方法体：
  - 如果 `self._tool_router` 为 None，返回 NOT_IMPLEMENTED
  - 如果 `self._shutting_down`（需新增状态标记），返回 `SHUTTING_DOWN`
  - 解析 `request.args` JSON（失败返回 `INVALID_ARGS_JSON`）
  - 调用 `await self._tool_router.execute(request.tool_name, args, request.timeout_ms)`
  - 返回 `tool_router.execute` 的结果

**预估**：~25 行变更 | **负责人**：CC（涉及 Servicer 核心逻辑替换）

### 7.4 Runner 端 RunnerEndpoint 扩展

- [ ] 修改 `src/plugin_runtime_v2/runner/endpoint.py` 中 `RunnerEndpoint.__init__`，新增 `plugin_loader: PluginLoader | None = None` 和 `tool_router: ToolRouter | None = None` 参数
- [ ] 将 `tool_router` 传递给 `_PluginRunnerServicer`
- [ ] 在 `_connect_and_handshake` 中 RegisterComponents 之前，如果 `plugin_loader` 不为 None：
  - 调用 `plugin_loader.load()` 收集声明
  - 用收集到的声明替换 `self._config.tools/events`（或直接构造 proto 声明用于 RegisterComponents）
- [ ] 在 `stop()` 中，如果 `plugin_loader` 不为 None，调用 `plugin_loader.unload()` 卸载插件

**预估**：~30 行变更 | **负责人**：CC（涉及 Runner 生命周期扩展）

### 7.5 RunnerConnection 补充 runner_listen_address

- [ ] 修改 `src/plugin_runtime_v2/host/connection.py` 中 `RunnerConnection`，新增 `runner_listen_address: str` 字段（默认空字符串）
- [ ] 在 `_PluginHostServicer.Connect` 握手阶段，将 `hello.runner_listen_address` 存储到 `conn.runner_listen_address`
- [ ] 此字段为 MCPToolProvider 创建 InvokeTool gRPC stub 的必要输入

**预估**：~10 行变更 | **负责人**：Codex（简单字段存储）

### 7.6 单元测试：回调注入

- [ ] 编写 `tests/plugin_runtime_v2/test_callback_injection.py`
- [ ] 测试 Servicer RegisterComponents 后 host_bridge.on_runner_registered 被调用
- [ ] 测试 Servicer _cleanup_connection 中 host_bridge.on_runner_disconnected 被调用
- [ ] 测试 Servicer 收到 EventPayload 后 host_bridge.on_event_received 被调用
- [ ] 测试 RunnerServicer InvokeTool 委托 tool_router.execute
- [ ] 测试 RunnerEndpoint start 中 plugin_loader.load 被调用

**预估**：~100 行 | **负责人**：Codex（依赖 7.1-7.5 完成后编写）

---

## 8. 集成验证与端到端测试

验证核心链路（ToolProvider 桥接 + Event 分发 + Tool 执行路由）端到端可用。

### 8.1 端到端测试：Tool 调用链路

- [ ] 编写 `tests/plugin_runtime_v2/integration/test_tool_chain.py`
- [ ] 测试场景：Runner 注册 → Host 创建 MCPToolProvider → ToolRegistry 注册 → ThinkingOrgan 调用 Tool → InvokeTool RPC → ToolRouter 执行 → 结果返回
- [ ] 使用 mock gRPC 通道模拟 Runner 和 Host 通信
- [ ] 验证 ToolExecutionResult 全链路正确

**预估**：~100 行 | **负责人**：CC（集成测试涉及多模块协作，需理解全链路）

### 8.2 端到端测试：Event 推送链路

- [ ] 编写 `tests/plugin_runtime_v2/integration/test_event_chain.py`
- [ ] 测试场景：插件 emit_event → RunnerEndpoint 推送 → Host 收到 EventPayload → EventDispatcher 分发
- [ ] 验证 Event 全链路正确

**预估**：~80 行 | **负责人**：Codex（依赖核心模块完成后编写）

### 8.3 端到端测试：@Command 上下文注入链路

- [ ] 编写 `tests/plugin_runtime_v2/integration/test_command_injection.py`
- [ ] 测试场景：@Command Tool 被 LLM 调用 → MCPHostBridge 注入上下文 → InvokeTool RPC 含上下文参数 → Runner 执行
- [ ] 验证上下文参数（session_id/sender_id/sender_name/is_group_chat）正确注入

**预估**：~80 行 | **负责人**：Codex（依赖 6.2 完成后编写）

### 8.4 端到端测试：@HomeCard 推送链路

- [ ] 编写 `tests/plugin_runtime_v2/integration/test_homecard_chain.py`
- [ ] 测试场景：插件 emit_card → PluginContext 构造 HomeCard 数据 → emit_event → Host 收到 → EventDispatcher 检测 card_metadata
- [ ] 验证 HomeCard 数据结构正确

**预估**：~60 行 | **负责人**：Codex（依赖核心模块完成后编写）

### 8.5 端到端测试：Runner 断开/重连

- [ ] 编写 `tests/plugin_runtime_v2/integration/test_runner_lifecycle.py`
- [ ] 测试场景：Runner 注册 → ToolProvider 注册 → Runner 断开 → ToolProvider 注销 → Runner 重连 → ToolProvider 重新注册
- [ ] 验证 ToolRegistry 中 Tool 的生命周期正确

**预估**：~80 行 | **负责人**：CC（涉及生命周期管理，需理解重连场景）

---

## 9. 代码审查与合规检查

最终验证确保交付质量，所有禁止项和约束条件满足。

### 9.1 禁止项检查

- [ ] 在 `src/plugin_runtime_v2/mcp/` 和 `src/plugin_runtime_v2/runner/` 目录下 grep `from src.plugin_runtime`，确认零匹配（v2 禁止导入 v1）
- [ ] 在 `src/plugin_runtime_v2/mcp/` 目录下 grep `global_config\|config_manager`，确认零匹配
- [ ] 审查 SDK v4 代码，确认不存在 `capabilities`/`capabilities_required` 术语
- [ ] 审查 SDK v4 代码，确认不存在 `stream_id` 参数名

**预估**：0 行变更 | **负责人**：CA（代码审查）

### 9.2 日志规范检查

- [ ] 确认所有 Phoenix-2 新增模块使用 `get_logger` 且模块名前缀为 `plugin_runtime_v2.`
- [ ] 确认 MCPToolProvider 注册/注销记录 INFO 日志
- [ ] 确认 MCPToolProvider invoke 失败记录 WARNING 日志
- [ ] 确认 EventDispatcher 分发记录 INFO 日志
- [ ] 确认 PluginLoader on_load 失败记录 ERROR 日志

**预估**：0 行变更 | **负责人**：CA（代码审查）

### 9.3 设计一致性核对

- [ ] 对照 design.md 接口清单，确认 MCPToolProvider/EventDispatcher/MCPHostBridge/PluginLoader/ToolRouter 的方法签名与设计一致
- [ ] 确认 ToolDeclaration → ToolSpec 映射规则与设计一致（x-maibot-command-pattern 剥离）
- [ ] 确认 InvokeToolResponse → ToolExecutionResult 映射规则与设计一致
- [ ] 确认 EventDispatcher.dispatch 接收单个 event_declaration（由 MCPHostBridge 预查找）
- [ ] 确认 MCPHostBridge.on_runner_registered 处理重连场景（先注销旧再注册新）
- [ ] 确认 PluginLoader.load/unload 为 async，内部用 inspect.iscoroutinefunction 判断

**预估**：0 行变更 | **负责人**：CA（代码审查）

### 9.4 性能约束验证

- [ ] 确认 MCPToolProvider.list_tools() 返回缓存列表，不重新构造
- [ ] 确认 ToolRouter 查找为 O(1)（dict 查找）
- [ ] 确认 MCPToolProvider invoke 全链路延迟可接受（同机通信 ≤50ms）

**预估**：0 行变更 | **负责人**：CA（代码审查）