# Phoenix-8：V1 兼容层插件 — 技术设计

## 1. 实现模型

### 1.1 上下文视图

兼容层插件 `maibot-team.v1-compat` 是一个 V4 插件，运行在 V4 Runner 进程中。它在 `on_load()` 时启动 V1 Runner 子进程，通过 V1 IPC 协议与子进程通信，将 V1 的组件和事件桥接到 V4 的 Tool/Event 模型。

```
┌─────────────────────────────────────────────────────┐
│ V4 Host (gRPC)                                      │
│  HostEndpoint → MCPHostBridge → EventDispatcher     │
└───────────────┬─────────────────────────────────────┘
                │ gRPC 双向流
┌───────────────▼─────────────────────────────────────┐
│ V4 Runner 进程                                       │
│  ┌─────────────────────────────────────────────────┐ │
│  │ V1CompatPlugin (MaiBotPlugin)                   │ │
│  │  on_load() → 启动 V1 Runner 子进程              │ │
│  │  @Tool("v1.invoke_component") → 泛化调度       │ │
│  │  @Event("v1.component_event") → 泛化事件        │ │
│  │  CompatBridge → V1 IPC Client                   │ │
│  └─────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
        │ V1 IPC (UDS/Named Pipe/TCP)
┌───────▼─────────────────────────────────────────────┐
│ V1 Runner 子进程                                     │
│  PluginRunner → PluginLoader → V1 插件们             │
│  PluginContext → cap.call → CompatBridge (IPC Host)  │
└─────────────────────────────────────────────────────┘
        │ 扫描 data/MaiMBot/plugins/
┌───────▼─────────────────────────────────────────────┐
│ V1 旧插件源码                                        │
│  _manifest.json v2 + plugin.py + maibot_sdk          │
└─────────────────────────────────────────────────────┘
```

### 1.2 服务/组件总体架构

兼容层由 3 个核心模块组成：

1. **CompatBridge** — V1 IPC 通信桥，管理 V1 Runner 子进程生命周期
2. **ComponentBridge** — 组件声明桥接，维护 V1 组件映射表，通过泛化调度 Tool 路由调用
3. **CapabilityBridge** — 能力调用桥接，将 V1 的 `cap.call` 路由到 V4 的 PluginContext

### 1.3 实现设计文档

#### 1.3.1 CompatBridge — V1 IPC 通信桥

**文件**：`plugins/maibot-team.v1-compat/compat_bridge.py`

**职责**：
- 启动/停止 V1 Runner 子进程
- 管理 V1 IPC Server（兼容层充当 V1 Host 角色）
- 处理 V1 Runner 的握手、组件注册、能力调用
- 健康检查与自动重启

**关键设计**：兼容层在 V4 Runner 进程内运行一个 **V1 IPC Server**，V1 Runner 子进程连接到这个 Server。这样兼容层完全复用 V1 的 IPC 协议，不需要修改 V1 Runner 代码。

**IPC 传输选择**：使用 TCP `127.0.0.1:0`（OS 分配随机端口），而非 UDS/Named Pipe。理由：跨平台一致、无 socket 文件残留清理问题、V1 Runner 的 `create_transport_client` 原生支持 TCP 地址格式。

```python
class CompatBridge:
    def __init__(self, config: CompatConfig):
        self._config = config
        self._ipc_server: RPCServer | None = None  # V1 IPC Host
        self._runner_process: asyncio.subprocess.Process | None = None
        self._component_registry = ComponentRegistry()  # V1 组件注册表
        self._restart_count = 0
        self._shutdown_event = asyncio.Event()

    async def start(self) -> None:
        # 1. 启动 V1 IPC Server
        # 2. 启动 V1 Runner 子进程
        # 3. 等待握手和就绪
        # 4. 启动健康检查循环

    async def stop(self) -> None:
        # 1. 发送 plugin.prepare_shutdown
        # 2. 发送 plugin.shutdown
        # 3. 等待子进程退出
        # 4. 停止 IPC Server

    async def invoke_component(self, method: str, plugin_id: str,
                                component_name: str, args: dict,
                                timeout_ms: int) -> dict:
        # 通过 V1 IPC 调用 V1 Runner 的组件

    async def _health_check_loop(self) -> None:
        # 定期检查 V1 Runner 子进程状态
```

**V1 IPC Server 注册的 RPC 方法**（兼容层充当 V1 Host，共 9 个）：

| 方法 | 处理逻辑 |
|------|---------|
| `runner.hello` | 校验 session_token，返回握手响应 |
| `plugin.bootstrap` | 记录插件能力需求，返回 `{accepted: True}` |
| `plugin.register_components` | 注册到 ComponentBridge，返回注册结果 |
| `plugin.register_plugin` | 兼容旧名，同 `plugin.register_components` |
| `plugin.unregister` | 从 ComponentBridge 移除组件 |
| `runner.ready` | 标记 V1 Runner 就绪 |
| `runner.log_batch` | 桥接到 V4 LoggerContext |
| `cap.call` | 路由到 CapabilityBridge |
| `host.route_message` | 通过 V4 `ctx.emit_event("v1.component_event")` 推送消息路由事件 |
| `host.update_message_gateway_state` | 记录网关状态变更日志 |

#### 1.3.2 ComponentBridge — 组件声明桥接（泛化调度）

**文件**：`plugins/maibot-team.v1-compat/component_bridge.py`

**核心设计**：V4 SDK 不支持运行时动态注册 Tool/Event（`MaiBotPlugin` 无 `register_tool()`/`register_event()` 方法），因此采用**泛化调度**方案：

- **1 个泛化 Tool**：`v1.invoke_component` — 所有 V1 的 Tool/Action/Command/API/LLM_PROVIDER 组件调用都走这个入口，通过 `component_name` 参数内部路由
- **1 个泛化 Event**：`v1.component_event` — 所有 V1 的 Event/Hook/Gateway 事件都走这个通道，通过 `event_type` 参数区分

**V1 组件类型 → 泛化调度映射**：

| V1 组件类型 | 调度通道 | invoke_method | 说明 |
|------------|---------|---------------|------|
| TOOL | `v1.invoke_component` | `plugin.invoke_tool` | component_name 参数路由 |
| ACTION | `v1.invoke_component` | `plugin.invoke_action` | ACTION 在 V1 内部已转为 TOOL |
| COMMAND | `v1.invoke_component` | `plugin.invoke_tool` | 命令模式保留在 metadata |
| API | `v1.invoke_component` | `plugin.invoke_api` | API 调用 |
| LLM_PROVIDER | `v1.invoke_component` | `plugin.invoke_llm_provider` | LLM Provider |
| EVENT_HANDLER | `v1.component_event` | — | 事件处理器 |
| HOOK_HANDLER | `v1.component_event` | — | Hook |
| MESSAGE_GATEWAY | `v1.component_event` | — | 消息网关 |
| HOME_CARD | `v1.component_event` | — | HomeCard 卡片数据 |

**关键约束**：V1 组件的 `invoke_method` 字段决定了 RPC 调用方式。ComponentBridge 内部维护 `component_name → V1ComponentMapping` 路由表，在收到 `v1.invoke_component` 调用时根据 `component_name` 查表路由。

```python
class ComponentBridge:
    def __init__(self, compat_bridge: CompatBridge):
        self._bridge = compat_bridge
        self._component_map: Dict[str, V1ComponentMapping] = {}  # component_name -> mapping
        self._plugin_components: Dict[str, List[str]] = {}  # plugin_id -> [component_names]

    def register_v1_components(self, plugin_id: str,
                                components: List[ComponentDeclaration]) -> None:
        # 将 V1 组件声明记录到内部路由表
        # 不注册独立的 V4 Tool/Event

    def unregister_plugin(self, plugin_id: str) -> None:
        # 移除该插件的所有组件映射

    async def invoke_component(self, component_name: str, args: dict) -> dict:
        # v1.invoke_component 的内部路由
        # 1. 从 _component_map 查找 component_name 对应的 V1ComponentMapping
        # 2. 提取 invoke_method、plugin_id
        # 3. 构造 InvokePayload 并通过 CompatBridge.invoke_component() 发送
        # 4. 返回结果

    def get_component_list(self) -> List[dict]:
        # 返回所有已注册 V1 组件的列表（用于 LLM 理解可用工具）
```

#### 1.3.3 CapabilityBridge — 能力调用桥接

**文件**：`plugins/maibot-team.v1-compat/capability_bridge.py`

**V1 `cap.call` → V4 PluginContext 映射**：

| V1 能力名 | V4 PluginContext 方法 | 说明 |
|-----------|---------------------|------|
| `send.text` | `ctx.send.text(session_id, text)` | stream_id → session_id |
| `send.emoji` | `ctx.send.emoji(session_id, emoji_base64)` | |
| `send.image` | `ctx.send.image(session_id, image_base64)` | |
| `send.forward` | `ctx.send.forward(session_id, message_id)` | |
| `send.hybrid` | `ctx.send.hybrid(session_id, segments)` | |
| `database.get` | `ctx.storage.get(key, default)` | |
| `database.save` / `database.set` | `ctx.storage.set(key, value)` | |
| `database.delete` | `ctx.storage.delete(key)` | |
| `config.get` / `config.get_plugin` | 从 CompatConfig 读取 | |
| `chat.get_*` | `ctx.get_session_info(session_id)` | 部分映射 |
| `emoji.get_random` | 无直接映射，返回空列表 | V4 SDK 无此 API |
| `llm.generate` | 无直接映射，返回错误 | V4 SDK 无 LLM Provider |
| `message.*` | 无直接映射，返回空 | V4 SDK 无消息查询 |

**关键约束**：V1 的 `cap.call` 能力调用通过 `PluginContext.rpc_call` 闭包发送到 V1 Host。兼容层作为 V1 Host，需要拦截这些调用并路由到 V4 的 PluginContext。

```python
class CapabilityBridge:
    def __init__(self, v4_ctx: PluginContext):
        self._ctx = v4_ctx

    async def handle_cap_call(self, plugin_id: str,
                              capability: str, args: dict) -> dict:
        # 路由 cap.call 到 V4 PluginContext
        handler = self._CAPABILITY_MAP.get(capability)
        if handler is None:
            return {"success": False, "error": f"capability '{capability}' not supported in v4 compat"}
        return await handler(self, args)
```

## 2. 接口设计

### 2.1 总体设计

兼容层插件对 V4 Host 暴露为标准 V4 插件，通过 1 个泛化 Tool + 1 个泛化 Event 声明组件。对 V1 Runner 暴露为标准 V1 Host，通过 V1 IPC 协议通信。

### 2.2 接口清单

| 接口 | 类型 | 方向 | 说明 |
|------|------|------|------|
| `v1.invoke_component` | @Tool | V4 Host → 兼容层 | 泛化调度：所有 V1 Tool/Action/Command/API/LLM_PROVIDER 组件调用 |
| `v1.component_event` | @Event | 兼容层 → V4 Host | 泛化事件：所有 V1 Event/Hook/Gateway/HomeCard 事件推送 |
| V1 IPC Server | RPC | V1 Runner → 兼容层 | V1 标准协议（9 个 RPC 方法） |
| V1 IPC Client | RPC | 兼容层 → V1 Runner | V1 标准协议（组件调用/关停） |

## 4. 数据模型

### 4.1 设计目标

兼容层需要维护 V1 组件的注册信息，用于在 V4 Tool 调用时路由到正确的 V1 RPC 方法。

### 4.2 模型实现

```python
@dataclass
class V1ComponentMapping:
    """V1 组件到泛化调度的映射记录。"""
    component_name: str         # V1 组件全名 (plugin_id.name)
    component_type: str         # V1 组件类型
    invoke_method: str          # V1 RPC 方法名（如 plugin.invoke_tool）
    plugin_id: str              # V1 插件 ID
    dispatch_channel: str       # "invoke_component" 或 "component_event"
    metadata: dict              # V1 组件元数据

@dataclass
class CompatConfig:
    """兼容层配置。"""
    v1_plugin_dir: str = "data/MaiMBot/plugins/"
    max_restart_attempts: int = 3
    restart_interval_sec: float = 5.0
    health_check_interval_sec: float = 30.0
    enabled: bool = True
    session_token: str = ""     # V1 IPC 握手令牌
```

## 3. 关键技术决策

### 3.1 兼容层充当 V1 Host

**决策**：兼容层在 V4 Runner 进程内运行一个 V1 IPC Server，V1 Runner 子进程连接到这个 Server。

**理由**：
- V1 Runner 的代码完全不需要修改
- V1 IPC 协议（MsgPack + 4-byte prefix）已有完整实现
- 兼容层可以完全控制 V1 Runner 的生命周期

**替代方案**：让 V1 Runner 连接到现有的 V1 Host（PluginRuntimeManager）
- 否决理由：V1 Host 在主进程中运行，兼容层无法控制其生命周期；V1 Host 的组件注册与 V4 的 Tool/Event 注册冲突

### 3.2 泛化调度 Tool

**决策**：使用 1 个泛化 Tool（`v1.invoke_component`）+ 1 个泛化 Event（`v1.component_event`）替代逐组件注册独立 V4 Tool/Event。

**理由**：
- V4 SDK 的 `MaiBotPlugin` 不支持运行时动态注册 Tool/Event（无 `register_tool()`/`register_event()` 方法）
- V1 组件在运行时才通过 `plugin.register_components` RPC 注册，无法在插件加载时用装饰器声明
- 泛化调度通过 `component_name`/`event_type` 参数内部路由，功能等价
- V1 组件变更（注册/注销）不需要重新 RegisterComponents

**替代方案**：为每个 V1 组件注册独立 V4 Tool/Event（`v1.tool.{plugin_id}.{name}`）
- 否决理由：V4 SDK 不支持动态注册；即使支持，大量 V1 组件会导致 RegisterComponents 消息过大

**LLM 可发现性**：`v1.invoke_component` Tool 的 `description` 包含当前所有可用 V1 组件列表，LLM 可据此选择正确的 `component_name`。

### 3.3 全量 Scope 声明

**决策**：兼容层声明所有可用 scope，用户一次性审批。

**理由**：
- V1 插件使用粗粒度 `capabilities_required`，无法映射到 V4 的细粒度 scope
- V1 插件数量多，逐个审批不现实
- 兼容层本身是可信组件（随主程序分发）

### 3.5 IPC 传输选择：TCP localhost

**决策**：CompatBridge 使用 TCP `127.0.0.1:0` 作为 IPC 传输，而非 UDS/Named Pipe。

**理由**：
- 跨平台一致：UDS 仅 Linux/macOS，Named Pipe 仅 Windows，TCP 三平台通用
- 无文件残留：UDS/Named Pipe 崩溃后需清理 socket 文件，TCP 无此问题
- V1 Runner 原生支持：`MAIBOT_IPC_ADDRESS=tcp://127.0.0.1:{port}` 格式，`create_transport_client` 自动创建 TCP 客户端
- 端口 0 让 OS 分配随机可用端口，不与已有服务冲突

**替代方案**：复用 V1 传输层的平台自动选择（UDS/Named Pipe/TCP）
- 否决理由：增加文件清理关注点，且跨平台行为不一致

**决策**：对无 V4 对应的能力（`emoji.*`、`llm.*`、`message.*`、`statistics.*` 等），返回空结果或错误。

**理由**：
- V4 SDK 当前不支持这些能力
- 大部分 V1 插件不依赖这些能力
- 未来可逐步扩展 CapabilityBridge