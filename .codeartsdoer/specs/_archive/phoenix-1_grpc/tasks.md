# Phoenix-1：gRPC 传输层 — 编码任务

## 1. 定义连接状态和数据模型

**执行者建议**：Codex（数据类定义，机械执行；ConnectionState 枚举 + dataclass 定义，逻辑简单）

**依赖**：无（Phoenix-0 proto 产出物已就绪）

### 1.1 实现 ConnectionState 枚举

- [ ] 在 `src/plugin_runtime_v2/host/connection.py` 中定义 `ConnectionState` 枚举：
  - 继承 `str, Enum`，6 个值：DISCONNECTED / CONNECTING / HANDSHAKING / REGISTERING / READY / CLOSING
  - 值为小写字符串：`"disconnected"` / `"connecting"` / `"handshaking"` / `"registering"` / `"ready"` / `"closing"`
  - 类级 docstring 说明每个状态的含义
- [ ] 验收：`ConnectionState("ready") == ConnectionState.READY` 为 True；`list(ConnectionState)` 长度为 6

### 1.2 实现 RunnerConnection 数据类

- [ ] 在 `src/plugin_runtime_v2/host/connection.py` 中定义 `RunnerConnection` dataclass：
  - 使用 `@dataclass(slots=True)`
  - 字段：runner_id(str), state(ConnectionState), sdk_version(str), session_token(str), scopes(list[str]), tools(list), events(list), plugin_id(str), plugin_version(str), connected_at(float=0.0), last_heartbeat_at(float=0.0), _heartbeat_misses(int=0)
  - 方法 `transition(new_state)`：校验状态转换合法性（按 design.md 2.1.3.1 的转换规则表），非法转换抛出 ValueError 并记录 ERROR 日志
  - 方法 `record_heartbeat()`：重置 `_heartbeat_misses=0`，更新 `last_heartbeat_at=time.time()`
  - 方法 `miss_heartbeat()`：`_heartbeat_misses+=1`，返回当前连续丢失次数
  - 方法 `to_snapshot()`：返回 `RunnerConnectionSnapshot` 不可变快照
- [ ] 验收：`RunnerConnection(runner_id="test", state=ConnectionState.CONNECTING, sdk_version="4.0.0", session_token="t", scopes=["message:send:text"]).transition(ConnectionState.HANDSHAKING)` 成功；`.transition(ConnectionState.READY)` 抛出 ValueError

### 1.3 实现 RunnerConnectionSnapshot 快照

- [ ] 在 `src/plugin_runtime_v2/host/connection.py` 中定义 `RunnerConnectionSnapshot` dataclass：
  - 使用 `@dataclass(frozen=True, slots=True)`
  - 字段：runner_id(str), state(str), sdk_version(str), scopes(tuple[str, ...]), plugin_id(str), plugin_version(str), tool_count(int), event_count(int), connected_at(float), last_heartbeat_at(float)
  - `state` 存储 `ConnectionState.value` 的字符串表示
- [ ] 验收：`RunnerConnectionSnapshot` 实例不可修改属性（`frozen=True`）；`snapshot.state == "ready"` 可用于 JSON 序列化

### 1.4 实现配置数据类

- [ ] 在 `src/plugin_runtime_v2/host/connection.py` 中定义 `HostEndpointConfig`：
  - 使用 `@dataclass(frozen=True, slots=True)`
  - 字段与默认值：listen_address("127.0.0.1:50051"), heartbeat_interval_s(30), heartbeat_timeout_s(10), max_heartbeat_misses(2), register_timeout_s(30), default_drain_timeout_ms(5000), max_runners(10), server_id("")（空字符串时自动生成 UUID v4）
  - `__post_init__` 中若 server_id 为空则生成 `uuid.uuid4().hex[:8]`
- [ ] 在 `src/plugin_runtime_v2/runner/reconnect.py` 中定义 `RunnerEndpointConfig`：
  - 使用 `@dataclass(frozen=True, slots=True)`
  - 字段与默认值：host_address(必填), runner_id("")(自动生成 UUID v4), sdk_version("")(自动读取 `"4.0.0"`), session_token(必填), scopes(list, 至少1项), tools(list), events(list), plugin_id(""), plugin_version("1.0.0"), reconnect_max_retries(10), reconnect_initial_delay_s(1.0), reconnect_max_delay_s(30.0), tool_timeout_ms(30000)
  - `__post_init__` 中若 runner_id 为空则生成 `uuid.uuid4().hex`
- [ ] 验收：`HostEndpointConfig()` 使用全部默认值创建成功；`RunnerEndpointConfig(host_address="localhost:50051", session_token="t", scopes=["message:send:text"])` 创建成功

## 2. 实现 Runner 连接注册表

**执行者建议**：Codex（定义清晰的分项任务，dict 封装 + 线程安全）

**依赖**：1（RunnerConnection 和 ConnectionState 已定义）

### 2.1 实现 RunnerRegistry

- [ ] 在 `src/plugin_runtime_v2/host/registry.py` 中定义 `RunnerRegistry` 类：
  - 内部属性 `_connections: dict[str, RunnerConnection]`
  - 方法 `register(conn: RunnerConnection) -> None`：注册连接，若 runner_id 已存在抛出 `ValueError("RUNNER_ALREADY_CONNECTED")`
  - 方法 `unregister(runner_id: str) -> None`：移除连接，不存在时静默忽略
  - 方法 `get(runner_id: str) -> RunnerConnection | None`：按 runner_id 查找
  - 方法 `get_all() -> dict[str, RunnerConnection]`：返回全部连接的浅拷贝
  - 方法 `has(runner_id: str) -> bool`：判断 runner_id 是否存在
  - 方法 `get_snapshot(runner_id: str) -> RunnerConnectionSnapshot | None`：返回指定 Runner 的快照
  - 方法 `get_all_snapshots() -> dict[str, RunnerConnectionSnapshot]`：返回所有 Runner 的快照字典
- [ ] 验收：`registry.register(conn)` 后 `registry.has("test")` 为 True；重复 register 同一 runner_id 抛出 ValueError；`get_all_snapshots()` 返回不可变快照

## 3. 实现心跳保活管理器

**执行者建议**：CC（异步定时器 + 回调，涉及 asyncio.Task 生命周期管理）

**依赖**：1（HostEndpointConfig 中的心跳参数已定义）

### 3.1 实现 HeartbeatManager

- [ ] 在 `src/plugin_runtime_v2/host/heartbeat.py` 中定义 `HeartbeatManager` 类：
  - 构造参数：interval_s(int), timeout_s(int), max_misses(int)
  - 内部属性：`_tasks: dict[str, asyncio.Task]`（每个 runner_id 一个心跳任务）
  - 方法 `start(runner_id, send_callback, timeout_callback) -> None`：
    - 为指定 runner_id 创建心跳定时器 asyncio.Task
    - `send_callback: Callable[[HeartbeatRequest], Awaitable[None]]` — 发送心跳请求
    - `timeout_callback: Callable[[str], Awaitable[None]]` — 心跳超时（判定断开）
    - 定时器逻辑：每隔 interval_s 调用 send_callback，若连续 max_misses 次未收到响应则调用 timeout_callback
  - 方法 `stop(runner_id: str) -> None`：取消指定 runner_id 的心跳任务
  - 方法 `stop_all() -> None`：取消所有心跳任务
  - 方法 `record_response(runner_id: str) -> None`：记录心跳响应，重置丢失计数
- [ ] 使用 `src/common/logger.py` 的 `get_logger("plugin_runtime_v2.host.heartbeat")`
- [ ] 心跳超时时记录 WARNING 日志，含 runner_id 和连续丢失次数
- [ ] 验收：启动心跳后 30s 内 send_callback 被调用；连续 2 次未响应后 timeout_callback 被调用

## 4. 实现重连策略

**执行者建议**：Codex（纯计算逻辑，指数退避算法）

**依赖**：1（RunnerEndpointConfig 中的重连参数已定义）

### 4.1 实现 ReconnectPolicy

- [ ] 在 `src/plugin_runtime_v2/runner/reconnect.py` 中定义 `ReconnectPolicy` 类：
  - 构造参数：max_retries(int), initial_delay_s(float), max_delay_s(float)
  - 内部属性：`_attempt: int = 0`
  - 方法 `next_delay() -> float | None`：
    - 若 `_attempt >= max_retries` 返回 None
    - 否则计算 `min(initial_delay_s * 2 ** _attempt, max_delay_s)`，`_attempt += 1`，返回延迟秒数
  - 方法 `reset() -> None`：`_attempt = 0`
- [ ] 验收：`ReconnectPolicy(10, 1.0, 30.0)` 连续调用 `next_delay()` 返回 1.0, 2.0, 4.0, 8.0, 16.0, 30.0, 30.0...；第 11 次返回 None；`reset()` 后从 1.0 重新开始

## 5. 实现 gRPC Host 服务

**执行者建议**：CC（核心流程，Connect 双向流处理涉及复杂异步逻辑和状态机交互）

**依赖**：1 + 2 + 3（数据模型、注册表、心跳管理器已就绪）

### 5.1 实现 PluginHostServicer — Connect 双向流握手

- [ ] 在 `src/plugin_runtime_v2/host/servicer.py` 中定义 `PluginHostServicer` 类，继承 `plugin_host_pb2_grpc.PluginHostServicer`：
  - 构造参数：registry(RunnerRegistry), heartbeat_mgr(HeartbeatManager), config(HostEndpointConfig)
  - 实现 `async Connect(request_iterator, context)` 方法：
    - 等待首条 RunnerMessage，验证 payload 为 hello
    - 首条消息非 hello：返回 `HostMessage(hello_response=HelloResponse(accepted=False, reason="FIRST_MESSAGE_MUST_BE_HELLO"))`，关闭流
    - 校验 HelloPayload 必填字段（runner_id, sdk_version, session_token, scopes）：缺失时返回 `accepted=False, reason="MISSING_REQUIRED_FIELD: {field}"`
    - runner_id 已存在：返回 `accepted=False, reason="RUNNER_ALREADY_CONNECTED"`
    - SDK 版本不兼容：返回 `accepted=False, reason="SDK_VERSION_MISMATCH"`
    - 校验通过：创建 RunnerConnection(state=HANDSHAKING)，注册到 RunnerRegistry，返回 `accepted=True, host_version, server_id`
    - `host_version` 来源：`importlib.metadata.version("maibot")`，读取失败时回退到 `"unknown"`
- [ ] 使用 `get_logger("plugin_runtime_v2.host.servicer")`
- [ ] 握手拒绝记录 INFO 日志，含 runner_id 和拒绝原因
- [ ] 验收：Runner 发送合法 HelloPayload → Host 返回 accepted=True；runner_id 重复 → accepted=False, reason="RUNNER_ALREADY_CONNECTED"

### 5.2 实现 PluginHostServicer — Connect 双向流消息循环

- [ ] 在 `Connect` 方法中，握手成功后进入消息循环：
  - 状态转为 REGISTERING
  - 启动心跳定时器：`heartbeat_mgr.start(runner_id, send_callback, timeout_callback)`
  - send_callback 构造 `HostMessage(heartbeat=HeartbeatRequest(timestamp_ms=...))` 写入双向流
  - timeout_callback 调用 `context.cancel()` 关闭流
  - 循环接收 RunnerMessage：
    - payload 为 event：处理 EventPayload，返回 `HostMessage(event_ack=EventAck(received=True))`，预留事件回调（Phoenix-2）
    - payload 为 heartbeat：调用 `heartbeat_mgr.record_response(runner_id)` 和 `conn.record_heartbeat()`
  - 流断开时：清理 RunnerConnection，从注册表移除，停止心跳，记录 INFO 日志
- [ ] 使用 `asyncio.Queue` 缓冲待发送的 HostMessage，避免双向流写入阻塞
- [ ] 验收：握手成功后 Host 持续接收 RunnerMessage；Runner 推送 Event → Host 返回 EventAck；Runner 发送 HeartbeatResponse → Host 更新心跳时间

### 5.3 实现 PluginHostServicer — RegisterComponents 一元 RPC

- [ ] 在 `PluginHostServicer` 中实现 `async RegisterComponents(request, context)` 方法：
  - 验证 plugin_id 非空：为空时返回 `accepted=False, reasons=["MISSING_PLUGIN_ID"]`
  - 验证 tools 和 events 列表中的 name 非空且无重复：重复时返回 `accepted=False, reasons=["DUPLICATE_TOOL_NAME: {name}"]`
  - 验证 runner_id 对应的 RunnerConnection 存在且状态为 REGISTERING：不存在时返回 `accepted=False, reasons=["RUNNER_NOT_FOUND"]`
  - 校验通过：将组件声明存储到 RunnerConnection，状态转为 READY，记录 connected_at，返回 `accepted=True`
- [ ] 验收：Runner 发送 RegisterComponentsRequest(tools=[ToolDeclaration(name="t1")], events=[EventDeclaration(name="e1")]) → Host 返回 accepted=True，RunnerConnection.tools 包含 t1

### 5.4 实现 PluginHostServicer — 注册超时处理

- [ ] 在 Connect 双向流握手成功后，启动注册超时定时器（register_timeout_s，默认 30s）：
  - 若 Runner 在超时内未发送 RegisterComponentsRequest，Host 主动关闭双向流
  - 超时定时器在收到 RegisterComponentsRequest 后取消
- [ ] 验收：握手成功后 30s 内未注册 → Host 关闭双向流，日志记录"Runner {runner_id} 注册超时"

## 6. 实现 gRPC Runner 服务

**执行者建议**：CC（RunnerEndpoint 涉及双向流管理 + 自动重连 + InvokeTool 服务端，复杂异步逻辑）

**依赖**：1 + 4（数据模型、重连策略已就绪）

### 6.1 实现 PluginRunnerServicer — InvokeTool 占位

- [ ] 在 `src/plugin_runtime_v2/runner/servicer.py` 中定义 `PluginRunnerServicer` 类，继承 `plugin_runner_pb2_grpc.PluginRunnerServicer`：
  - 实现 `async InvokeTool(request, context)` 方法：
    - Phoenix-1 阶段返回 `InvokeToolResponse(success=False, error="NOT_IMPLEMENTED")`
    - 记录 INFO 日志，含 tool_name
- [ ] 验收：Host 调用 InvokeTool(tool_name="test") → Runner 返回 success=False, error="NOT_IMPLEMENTED"

### 6.2 实现 RunnerEndpoint — 连接与握手

- [ ] 在 `src/plugin_runtime_v2/runner/endpoint.py` 中定义 `RunnerEndpoint` 类：
  - 构造参数：config(RunnerEndpointConfig)
  - 内部属性：`_channel: grpc.aio.Channel | None`, `_state: ConnectionState`, `_reconnect: ReconnectPolicy`, `_servicer: PluginRunnerServicer`, `_server: grpc.aio.Server | None`
  - 实现 `async start() -> None`：
    - 创建 gRPC 通道（配置 keepalive 参数，见 design.md 2.3.2.4 的 GRPC_CHANNEL_OPTIONS）
    - 启动 PluginRunner gRPC 服务端（随机端口）
    - 调用 Connect 双向流，发送 HelloPayload
    - 等待 HelloResponse：
      - accepted=True：调用 RegisterComponents
      - accepted=False：记录 ERROR 日志，不重连，状态转为 DISCONNECTED
- [ ] 使用 `get_logger("plugin_runtime_v2.runner.endpoint")`
- [ ] 验收：RunnerEndpoint.start() → 状态从 DISCONNECTED 经 CONNECTING → HANDSHAKING → REGISTERING → READY

### 6.3 实现 RunnerEndpoint — RegisterComponents 调用

- [ ] 在 `start()` 方法中，握手成功后调用 RegisterComponents：
  - 创建 PluginHostStub，调用 `stub.RegisterComponents(RegisterComponentsRequest(...))`
  - 传入 config.tools, config.events, config.plugin_id, config.plugin_version
  - accepted=True：状态转为 READY
  - accepted=False：记录 ERROR 日志，状态转为 DISCONNECTED，进入重连
- [ ] 验收：握手成功后自动调用 RegisterComponents → 注册成功后状态为 READY

### 6.4 实现 RunnerEndpoint — 双向流接收循环

- [ ] 在 `start()` 方法中，注册成功后启动双向流接收循环：
  - 循环读取 HostMessage：
    - payload 为 heartbeat：发送 `RunnerMessage(heartbeat=HeartbeatResponse(timestamp_ms=...))`
    - payload 为 shutdown：触发优雅关停流程
    - payload 为 event_ack：记录日志（预留，Phoenix-2 使用）
  - 流断开时：状态转为 DISCONNECTED，进入重连
- [ ] 验收：Host 发送 HeartbeatRequest → Runner 回复 HeartbeatResponse；Host 发送 ShutdownRequest → Runner 触发关停

### 6.5 实现 RunnerEndpoint — emit_event

- [ ] 实现 `async emit_event(event_name: str, payload: dict[str, Any]) -> None`：
  - 前置条件：状态为 READY
  - 构造 `RunnerMessage(event=EventPayload(event_name=event_name, payload=json.dumps(payload)))`
  - 通过双向流发送
  - 状态非 READY 时抛出 `ConnectionError("Runner not in READY state")`
- [ ] 验收：`emit_event("test", {"key": "value"})` → Host 收到 RunnerMessage(event=EventPayload)

### 6.6 实现 RunnerEndpoint — 自动重连

- [ ] 在双向流断开时，进入重连逻辑：
  - 使用 ReconnectPolicy 计算退避延迟
  - 每次重连：重新创建 gRPC 通道 → Connect 双向流 → HelloPayload → RegisterComponents
  - 重连耗尽（next_delay() 返回 None）：记录 ERROR 日志，状态保持 DISCONNECTED 终态
  - 重连成功：reset() 重连策略
- [ ] 验收：Host 重启后 Runner 自动重连并重新握手+注册；重连 10 次失败后停止重试

### 6.7 实现 RunnerEndpoint — 优雅关停

- [ ] 在收到 ShutdownRequest 后：
  - 停止接受新的 InvokeTool 调用（PluginRunnerServicer 返回 `success=False, error="SHUTTING_DOWN"`）
  - 等待正在执行的 Tool 调用完成（不超过 drain_timeout_ms）
  - 在 drain_timeout_ms 内主动关闭双向流
- [ ] 实现 `async stop() -> None`：
  - 关闭双向流
  - 停止 PluginRunner gRPC 服务端
  - 关闭 gRPC 通道
  - 状态转为 DISCONNECTED
- [ ] 验收：收到 ShutdownRequest(drain_timeout_ms=5000) → 5s 内双向流关闭；stop() 后状态为 DISCONNECTED

## 7. 实现 HostEndpoint 公共 API

**执行者建议**：CC（生命周期管理 + 优雅关停 + 多 Runner 协调，高风险文件）

**依赖**：5 + 3（Servicer、心跳管理器已就绪）

### 7.1 实现 HostEndpoint — 启动

- [ ] 在 `src/plugin_runtime_v2/host/endpoint.py` 中定义 `HostEndpoint` 类：
  - 构造参数：config(HostEndpointConfig)
  - 内部属性：`_server: grpc.aio.Server | None`, `_registry: RunnerRegistry`, `_heartbeat_mgr: HeartbeatManager`, `_servicer: PluginHostServicer`
  - 实现 `async start() -> None`：
    - 创建 `grpc.aio.Server`（配置 keepalive 参数，见 design.md 2.3.2.4 的 GRPC_SERVER_OPTIONS）
    - 注册 PluginHostServicer
    - 启用 gRPC 反射服务（`grpc_reflection`）
    - 绑定监听地址 `config.listen_address`
    - 启动服务器
- [ ] 使用 `get_logger("plugin_runtime_v2.host.endpoint")`
- [ ] 验收：`HostEndpoint(HostEndpointConfig()).start()` 后 gRPC 反射服务可见 PluginHost 服务定义

### 7.2 实现 HostEndpoint — 优雅关停

- [ ] 实现 `async stop() -> None`：
  - 遍历所有已连接的 Runner，发送 ShutdownRequest(reason="host_shutdown", drain_timeout_ms=config.default_drain_timeout_ms)
  - 等待 drain_timeout_ms
  - 强制关闭所有仍在连接的 Runner 的双向流
  - 停止心跳管理器
  - 停止 gRPC 服务器（grace=5s）
  - 清空注册表
- [ ] 验收：`stop()` 后所有 Runner 收到 ShutdownRequest，gRPC 服务器停止

### 7.3 实现 HostEndpoint — get_status

- [ ] 实现 `get_status() -> dict[str, RunnerConnectionSnapshot]`：
  - 返回 `_registry.get_all_snapshots()`
- [ ] 实现 `listen_address` 属性：返回实际监听地址
- [ ] 验收：`get_status()` 返回所有 Runner 的连接状态快照，可 JSON 序列化

## 8. 更新模块导出和禁止项验证

**执行者建议**：Codex（机械执行，__init__.py 更新 + grep 验证）

**依赖**：5 + 6 + 7（所有模块已实现）

### 8.1 更新 host/__init__.py 导出

- [ ] 在 `src/plugin_runtime_v2/host/__init__.py` 中导出公共 API：
  - `HostEndpoint`, `HostEndpointConfig`
  - `ConnectionState`, `RunnerConnection`, `RunnerConnectionSnapshot`
  - `RunnerRegistry`
- [ ] 验收：`from src.plugin_runtime_v2.host import HostEndpoint, ConnectionState` 成功

### 8.2 更新 runner/__init__.py 导出

- [ ] 在 `src/plugin_runtime_v2/runner/__init__.py` 中导出公共 API：
  - `RunnerEndpoint`, `RunnerEndpointConfig`
  - `ReconnectPolicy`
- [ ] 验收：`from src.plugin_runtime_v2.runner import RunnerEndpoint, RunnerEndpointConfig` 成功

### 8.3 验证 v1 隔离禁止项

- [ ] 在 `src/plugin_runtime_v2/host/` 下执行 `grep -r "from src.plugin_runtime" .`，确认零匹配
- [ ] 在 `src/plugin_runtime_v2/runner/` 下执行 `grep -r "from src.plugin_runtime" .`，确认零匹配
- [ ] 在 `src/plugin_runtime_v2/host/` 下执行 `grep -r "global_config\|config_manager" .`，确认零匹配
- [ ] 在 `src/plugin_runtime_v2/runner/` 下执行 `grep -r "global_config\|config_manager" .`，确认零匹配
- [ ] 验收：v2 目录无任何对 v1 的交叉引用，无 global_config/config_manager 导入

## 9. 集成验证

**执行者建议**：CC（需要理解全局架构，验证 Host↔Runner 端到端流程）

**依赖**：8（所有模块已实现并导出）

### 9.1 Host↔Runner 连接生命周期端到端测试

- [ ] 编写测试脚本，验证完整连接生命周期：
  - 启动 HostEndpoint
  - 启动 RunnerEndpoint，验证状态从 DISCONNECTED → READY
  - Runner 调用 emit_event，验证 Host 收到 EventPayload
  - Host 调用 Runner 的 InvokeTool（通过 gRPC stub），验证返回 NOT_IMPLEMENTED
  - Host 发送 ShutdownRequest，验证 Runner 在 drain_timeout 内关闭
  - Host 调用 stop()，验证优雅关停
- [ ] 验收：端到端流程无异常，所有状态转换正确

### 9.2 心跳保活端到端验证

- [ ] 编写测试脚本，验证心跳机制：
  - Host 和 Runner 连接成功后，等待 30s
  - 验证 Host 发送了 HeartbeatRequest
  - 验证 Runner 回复了 HeartbeatResponse
  - 模拟 Runner 停止回复心跳（断开双向流）
  - 验证 Host 在 60s 内判定 Runner 断开并清理连接
- [ ] 验收：心跳正常交换；连续 2 次超时后 Host 判定断开

### 9.3 Runner 自动重连端到端验证

- [ ] 编写测试脚本，验证重连机制：
  - Host 和 Runner 连接成功
  - 重启 Host（stop + start）
  - 验证 Runner 自动重连并重新握手+注册
  - 验证重连后状态为 READY
  - 模拟 Host 持续不可用，验证 Runner 重连 10 次后停止
- [ ] 验收：Host 重启后 Runner 自动重连成功；重连耗尽后 Runner 进入 DISCONNECTED 终态

### 9.4 多 Runner 并行连接验证

- [ ] 编写测试脚本，验证多 Runner 并行：
  - 启动 HostEndpoint
  - 启动 3 个 RunnerEndpoint，使用不同 runner_id
  - 验证 Host 注册表中有 3 个 RunnerConnection
  - 验证每个 Runner 的心跳独立
  - 断开其中一个 Runner，验证其他 Runner 不受影响
- [ ] 验收：3 个 Runner 同时连接正常；断开一个不影响其他

### 9.5 异常场景验证

- [ ] 验证重复 runner_id 连接被拒绝
- [ ] 验证首条消息非 HelloPayload 被拒绝
- [ ] 验证 SDK 版本不兼容被拒绝
- [ ] 验证 RegisterComponents 中组件名称重复被拒绝
- [ ] 验证注册超时（30s 未注册）Host 主动关闭
- [ ] 验证关停期间新的 InvokeTool 调用返回 SHUTTING_DOWN
- [ ] 验收：所有异常场景按 spec.md 5.1.3 / 5.2.3 / 5.3.3 定义的行为正确处理

### 9.6 性能基线验证

- [ ] 验证 gRPC 双向流单条消息（≤4KB）端到端延迟 ≤5ms（同机通信，不含业务逻辑）
- [ ] 验证 InvokeTool 一元 RPC 的 gRPC 层开销 ≤2ms（同机通信）
- [ ] 验证 Host 支持至少 10 个 Runner 同时连接
- [ ] 验收：性能指标满足 spec.md 4.1 的要求

## 10. 代码审查与文档

**执行者建议**：CA（代码审查 + 质量守卫）

**依赖**：9（集成验证通过）

### 10.1 代码审查

- [ ] 审查 `src/plugin_runtime_v2/host/` 所有文件：ConnectionState 转换规则与 design.md 一致、RunnerConnection 线程安全、日志规范
- [ ] 审查 `src/plugin_runtime_v2/runner/` 所有文件：重连逻辑正确性、优雅关停流程、gRPC keepalive 配置
- [ ] 审查禁止项：v2 无 v1 交叉引用、无 global_config 导入
- [ ] 验收：审查记录无关键问题

### 10.2 设计与实现一致性核对

- [ ] 核对 HostEndpoint 接口签名与 design.md 2.2.2.1 一致
- [ ] 核对 RunnerEndpoint 接口签名与 design.md 2.2.2.2 一致
- [ ] 核对 ConnectionState 枚举值与 design.md 2.2.2.5 一致
- [ ] 核对 RunnerConnection 字段与 design.md 2.2.2.6 一致
- [ ] 核对 gRPC keepalive 配置与 design.md 2.3.2.4 一致
- [ ] 验收：所有接口签名和配置参数与设计文档一致

### 10.3 变更范围确认

- [ ] 确认所有新增文件均在 `src/plugin_runtime_v2/` 内
- [ ] 确认未修改 `src/plugin_runtime/` 下的任何 v1 代码
- [ ] 确认未修改 `src/plugin_runtime_v2/proto/` 下的 .proto 文件
- [ ] 确认未修改 `src/plugin_runtime_v2/scope/` 下的任何代码
- [ ] 验收：变更范围与 Phoenix-1 职责边界一致