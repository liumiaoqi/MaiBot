# Phoenix-8：V1 兼容层插件 — 实现任务

## 任务总览

| 编号 | 任务 | 依赖 | 预估复杂度 | 建议执行者 |
|------|------|------|-----------|-----------|
| T1 | 插件骨架 + Manifest + CompatConfig | 无 | 中 | CC |
| T2 | CompatBridge — V1 IPC Server + 子进程管理 | T1 | 高 | CC |
| T3 | ComponentBridge — 泛化调度路由 | T2 | 中 | CC |
| T4 | CapabilityBridge — 能力调用桥接 | T2 | 中 | Codex |
| T5 | V1CompatPlugin 主类集成 | T2, T3, T4 | 中 | CC |
| T6 | 单元测试 | T5 | 中 | Codex |
| T7 | 集成验证 | T6 | 高 | 用户/CA |

---

## T1：插件骨架 + Manifest + CompatConfig

**目标**：创建兼容层插件的目录结构和基础文件。

**文件清单**：
- `plugins/maibot-team.v1-compat/__init__.py` — `create_plugin()` 入口
- `plugins/maibot-team.v1-compat/plugin.py` — V1CompatPlugin 类骨架（仅 `on_load`/`on_unload` 占位）
- `plugins/maibot-team.v1-compat/_manifest.json` — Manifest v3
- `plugins/maibot-team.v1-compat/config.py` — CompatConfig 数据类

**Manifest v3 内容**：
```json
{
  "manifest_version": 3,
  "id": "maibot-team.v1-compat",
  "name": "V1 Compatibility Layer",
  "version": "1.0.0",
  "description": "Bridge V1 plugins to V4 runtime via generalized dispatch",
  "author": "MaiBot Team",
  "scopes": [
    "message:send", "message:send:emoji", "message:send:image",
    "message:send:forward", "message:send:hybrid",
    "database:read", "database:write", "database:delete",
    "session:read", "config:read",
    "plugin:read", "plugin:manage"
  ]
}
```

**CompatConfig 字段**：
```python
@dataclass
class CompatConfig:
    v1_plugin_dir: str = "data/MaiMBot/plugins/"
    max_restart_attempts: int = 3
    restart_interval_sec: float = 5.0
    health_check_interval_sec: float = 30.0
    enabled: bool = True
```

**验收条件**：
- [ ] `plugins/maibot-team.v1-compat/` 目录存在且包含 4 个文件
- [ ] `_manifest.json` 为合法 Manifest v3 格式
- [ ] `from plugins.maibot_team.v1_compat import create_plugin` 不报错
- [ ] `CompatConfig` 可实例化且默认值正确

---

## T2：CompatBridge — V1 IPC Server + 子进程管理

**目标**：实现兼容层的核心通信桥，在 V4 Runner 进程内运行 V1 IPC Server，启动和管理 V1 Runner 子进程。

**文件**：`plugins/maibot-team.v1-compat/compat_bridge.py`

**核心实现**：

### 2a. V1 IPC Server（兼容层充当 V1 Host）

复用 V1 的 `RPCServer` + `MsgPackCodec` + `TransportServer`，注册以下 **9 个** RPC 方法（与 V1 Supervisor 的 `_register_internal_methods` 对齐）：

| 方法 | 处理逻辑 |
|------|---------|
| `runner.hello` | 校验 session_token，返回 `HelloResponsePayload(accepted=True)` |
| `plugin.bootstrap` | 记录插件能力需求，返回 `{accepted: True}` |
| `plugin.register_components` | 委托给 ComponentBridge.register_v1_components()，返回注册结果 |
| `plugin.register_plugin` | 兼容旧名，同 `plugin.register_components` |
| `plugin.unregister` | 委托给 ComponentBridge.unregister_plugin() |
| `runner.ready` | 标记 V1 Runner 就绪，设置 `_ready_event` |
| `runner.log_batch` | 桥接到 V4 `ctx.logger` |
| `cap.call` | 委托给 CapabilityBridge.handle_cap_call() |
| `host.route_message` | 通过 V4 `ctx.emit_event("v1.component_event")` 推送消息路由事件 |
| `host.update_message_gateway_state` | 记录网关状态变更日志 |

**关键约束**：
- 必须从 `src.plugin_runtime.protocol` 导入 `RPCServer`、`MsgPackCodec`、`Envelope`、各 Payload 模型
- 必须从 `src.plugin_runtime.protocol.transport` 导入 `create_transport_server`
- IPC 地址使用 TCP `127.0.0.1:0`（OS 分配随机端口），跨平台一致且无 socket 文件残留问题
- V1 Runner 的 `create_transport_client` 原生支持 `tcp://127.0.0.1:{port}` 地址格式
- session_token 在 `CompatBridge.__init__` 中生成（`secrets.token_hex(32)`），通过环境变量传递给子进程

### 2b. V1 Runner 子进程管理

```python
async def start(self) -> None:
    # 1. 启动 V1 IPC Server（监听 TCP 127.0.0.1:0）
    # 2. 获取实际分配的端口号
    # 3. 构建子进程环境变量：
    #    MAIBOT_IPC_ADDRESS = tcp://127.0.0.1:{port}    #    MAIBOT_SESSION_TOKEN = session_token
    #    MAIBOT_PLUGIN_DIRS = config.v1_plugin_dir
    #    MAIBOT_HOST_VERSION = "v1-compat-1.0.0"
    #    MAIBOT_RUNNER_GROUP = "v1_compat"
    #    MAIBOT_EXTERNAL_PLUGIN_IDS = "{}"
    #    MAIBOT_BLOCKED_PLUGIN_REASONS = "{}"
    # 4. spawn: python -m src.plugin_runtime.runner.runner_main
    # 5. 等待握手（_wait_for_runner_connection，10s 超时）
    # 6. 等待就绪（_wait_for_runner_ready，60s 超时）
    # 7. 启动健康检查循环

async def stop(self) -> None:
    # 1. 发送 plugin.prepare_shutdown RPC 请求
    # 2. 发送 plugin.shutdown RPC 请求
    # 3. 等待子进程退出（5s 超时 → terminate → 3s → kill）
    # 4. 停止 IPC Server
```

### 2c. 健康检查与自动重启

```python
async def _health_check_loop(self) -> None:
    # 定期（config.health_check_interval_sec）发送 plugin.health RPC
    # 若子进程退出：
    #   - restart_count < max_restart_attempts → 重启（间隔 = base × 2^attempt）
    #   - restart_count >= max_restart_attempts → 停止重启，记录错误

async def invoke_component(self, method: str, plugin_id: str,
                            component_name: str, args: dict,
                            timeout_ms: int = 30000) -> dict:
    # 通过 V1 IPC 发送 RPC 请求到 V1 Runner
    # 构造 Envelope(method=method, plugin_id=plugin_id, payload={...})
    # 等待响应，超时返回错误
```

**验收条件**：
- [ ] CompatBridge 可启动 V1 IPC Server 并监听 TCP 端口
- [ ] V1 Runner 子进程可成功握手（`runner.hello` → `HelloResponsePayload(accepted=True)`）
- [ ] V1 Runner 子进程可成功就绪（`runner.ready` → `_ready_event.set()`）
- [ ] 9 个 RPC 方法全部注册并可响应
- [ ] CompatBridge.stop() 可优雅关停 V1 Runner 子进程
- [ ] 子进程崩溃后可自动重启（最多 3 次）
- [ ] 连续崩溃 3 次后停止重启并记录错误日志

---

## T3：ComponentBridge — 泛化调度路由

**目标**：维护 V1 组件的内部路由表，通过泛化调度 Tool（`v1.invoke_component`）路由 V1 组件调用。

**文件**：`plugins/maibot-team.v1-compat/component_bridge.py`

**核心设计**：V4 SDK 不支持运行时动态注册 Tool/Event，因此采用泛化调度方案——所有 V1 组件调用走同一个 `v1.invoke_component` Tool，内部通过 `component_name` 路由。

### 3a. V1 组件类型 → 泛化调度映射

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

### 3b. 注册流程

```python
def register_v1_components(self, plugin_id: str,
                            components: List[ComponentDeclaration]) -> None:
    # 1. 先移除该插件的旧组件映射（unregister_plugin）
    # 2. 遍历 components
    # 3. 根据 component_type 确定 invoke_method 和 dispatch_channel
    # 4. 存储 V1ComponentMapping 到 _component_map
    # 5. 更新 _plugin_components 索引
    # 注意：不注册独立的 V4 Tool/Event，仅维护内部路由表

def unregister_plugin(self, plugin_id: str) -> None:
    # 移除该插件的所有组件映射
```

### 3c. 泛化调度 Tool 路由

```python
async def invoke_component(self, component_name: str, args: dict) -> dict:
    # v1.invoke_component 的内部路由
    # 1. 从 _component_map 查找 component_name 对应的 V1ComponentMapping
    # 2. 若未找到，返回 {"success": False, "error": f"component '{component_name}' not found"}
    # 3. 提取 invoke_method、plugin_id
    # 4. 构造 InvokePayload(component_name=name, args=args)
    # 5. 通过 CompatBridge.invoke_component() 发送 RPC
    # 6. 返回结果
```

### 3d. 组件列表查询

```python
def get_component_list(self) -> List[dict]:
    # 返回所有已注册 V1 组件的列表
    # 用于 v1.invoke_component Tool 的 description，让 LLM 知道有哪些可用组件
    # 格式：[{"component_name": "...", "type": "...", "description": "..."}]
```

**数据模型**：
```python
@dataclass
class V1ComponentMapping:
    component_name: str         # V1 组件全名 (plugin_id.name)
    component_type: str         # V1 组件类型
    invoke_method: str          # V1 RPC 方法名（如 plugin.invoke_tool）
    plugin_id: str              # V1 插件 ID
    dispatch_channel: str       # "invoke_component" 或 "component_event"
    metadata: dict              # V1 组件元数据
```

**验收条件**：
- [ ] V1 的 7 种组件类型均可正确映射到泛化调度通道
- [ ] invoke_component() 可根据 component_name 正确路由到 V1 RPC 方法
- [ ] 重复注册同一插件时，先移除旧组件再注册新组件
- [ ] get_component_list() 返回正确的组件列表
- [ ] 未找到组件时返回错误而非抛异常

---

## T4：CapabilityBridge — 能力调用桥接

**目标**：将 V1 的 `cap.call` 能力调用路由到 V4 的 PluginContext 对应方法。

**文件**：`plugins/maibot-team.v1-compat/capability_bridge.py`

**核心实现**：

### 4a. 能力映射表

| V1 能力名 | V4 PluginContext 方法 | 参数转换 |
|-----------|---------------------|---------|
| `send.text` | `ctx.send.text(session_id, text)` | args.stream_id → session_id |
| `send.emoji` | `ctx.send.emoji(session_id, emoji_base64)` | — |
| `send.image` | `ctx.send.image(session_id, image_base64)` | — |
| `send.forward` | `ctx.send.forward(session_id, message_id)` | — |
| `send.hybrid` | `ctx.send.hybrid(session_id, segments)` | — |
| `database.get` | `ctx.storage.get(key, default)` | — |
| `database.save` / `database.set` | `ctx.storage.set(key, value)` | — |
| `database.delete` | `ctx.storage.delete(key)` | — |
| `config.get` / `config.get_plugin` | 从 CompatConfig 读取 | — |
| `chat.get_*` | `ctx.get_session_info(session_id)` | 部分映射 |

### 4b. 无 V4 对应的能力

| V1 能力名 | 处理方式 | 理由 |
|-----------|---------|------|
| `emoji.get_random` | 返回 `{"success": False, "error": "not supported in v4"}` | V4 SDK 无此 API |
| `llm.generate` | 返回 `{"success": False, "error": "not supported in v4"}` | V4 SDK 无 LLM Provider |
| `message.*` | 返回 `{"success": False, "error": "not supported in v4"}` | V4 SDK 无消息查询 |
| `statistics.*` | 返回空结果 | V4 SDK 无统计 |
| `knowledge.*` | 返回空结果 | V4 SDK 无知识库 |
| `render.*` | 返回空结果 | V4 SDK 无渲染 |
| `person.*` | 返回空结果 | V4 SDK 无人物查询 |
| `tool.*` | 返回空结果 | V4 SDK 无工具查询 |
| `maisaka.*` | 返回空结果 | V4 SDK 无 maisaka |

### 4c. 核心逻辑

```python
class CapabilityBridge:
    def __init__(self, v4_ctx: PluginContext):
        self._ctx = v4_ctx
        self._CAPABILITY_MAP: Dict[str, Callable] = {
            "send.text": self._handle_send_text,
            "send.emoji": self._handle_send_emoji,
            "database.get": self._handle_db_get,
            "database.save": self._handle_db_save,
            # ...
        }

    async def handle_cap_call(self, plugin_id: str,
                               capability: str, args: dict) -> dict:
        handler = self._CAPABILITY_MAP.get(capability)
        if handler is None:
            return {"success": False, "error": f"capability '{capability}' not supported in v4 compat"}
        try:
            return await handler(args)
        except Exception as e:
            return {"success": False, "error": str(e)}
```

**验收条件**：
- [ ] `send.text` 可通过 V4 `ctx.send.text` 发送消息
- [ ] `database.get/save/delete` 可通过 V4 `ctx.storage` 读写
- [ ] 无 V4 对应的能力返回 `{"success": False, "error": "..."}` 而非抛异常
- [ ] `stream_id → session_id` 参数转换正确

---

## T5：V1CompatPlugin 主类集成

**目标**：将 CompatBridge、ComponentBridge、CapabilityBridge 集成到 V1CompatPlugin 主类中，实现完整的 `on_load`/`on_unload` 生命周期。

**文件**：`plugins/maibot-team.v1-compat/plugin.py`

**核心实现**：

```python
class V1CompatPlugin(MaiBotPlugin):
    def __init__(self):
        super().__init__()
        self._config = CompatConfig()
        self._compat_bridge: CompatBridge | None = None
        self._component_bridge: ComponentBridge | None = None
        self._capability_bridge: CapabilityBridge | None = None

    @Tool("v1.invoke_component")
    async def invoke_component(self, component_name: str, args: dict) -> dict:
        """调用 V1 兼容层组件。可用组件列表：{动态更新}"""
        return await self._component_bridge.invoke_component(component_name, args)

    @Event("v1.component_event")
    async def on_component_event(self, event_data: dict) -> None:
        """接收 V1 兼容层事件。"""
        pass

    async def on_load(self, ctx: PluginContext) -> None:
        # 1. 读取配置
        # 2. 创建 CapabilityBridge（需要 ctx）
        # 3. 创建 ComponentBridge（需要 compat_bridge 引用）
        # 4. 创建 CompatBridge（需要 config, component_bridge, capability_bridge）
        # 5. 启动 CompatBridge（启动 V1 Runner 子进程，等待就绪）
        # 6. V1 插件注册完成后，更新 invoke_component 的 description

    async def on_unload(self, ctx: PluginContext) -> None:
        # 1. 停止 CompatBridge
        # 2. 清理资源
```

### 5a. 泛化调度 vs 动态注册

**不需要动态注册**：`v1.invoke_component` 和 `v1.component_event` 在插件代码中用装饰器静态声明，V1 组件的变更只影响 ComponentBridge 的内部路由表，不需要重新注册 V4 Tool/Event。

**LLM 可发现性**：`v1.invoke_component` 的 `description` 在 `on_load` 完成后动态更新，包含当前所有可用 V1 组件列表。

**验收条件**：
- [ ] `on_load()` 可启动 V1 Runner 子进程并等待就绪
- [ ] `v1.invoke_component` Tool 可通过 component_name 路由到正确的 V1 组件
- [ ] `v1.component_event` Event 可接收 V1 事件
- [ ] `on_unload()` 可优雅关停 V1 Runner 子进程
- [ ] 兼容层崩溃不影响其他 V4 插件

---

## T6：单元测试

**目标**：为兼容层的核心模块编写单元测试。

**文件**：`tests/plugin_runtime_v2/test_v1_compat.py`

**测试用例**：

### 6a. ComponentBridge 测试

| 用例 | 描述 |
|------|------|
| `test_tool_dispatch` | V1 TOOL → invoke_component 调度正确（invoke_method = plugin.invoke_tool） |
| `test_action_dispatch` | V1 ACTION → invoke_component 调度正确（invoke_method = plugin.invoke_action） |
| `test_command_dispatch` | V1 COMMAND → invoke_component 调度正确 |
| `test_event_handler_channel` | V1 EVENT_HANDLER → component_event 通道 |
| `test_hook_channel` | V1 HOOK_HANDLER → component_event 通道 |
| `test_gateway_channel` | V1 MESSAGE_GATEWAY → component_event 通道 |
| `test_component_not_found` | 调用不存在的 component_name 返回错误 |
| `test_duplicate_registration` | 重复注册先移除旧组件 |
| `test_get_component_list` | get_component_list() 返回正确的组件列表 |

### 6b. CapabilityBridge 测试

| 用例 | 描述 |
|------|------|
| `test_send_text_bridge` | `send.text` → `ctx.send.text` 参数转换正确 |
| `test_db_get_bridge` | `database.get` → `ctx.storage.get` |
| `test_db_set_bridge` | `database.save` → `ctx.storage.set` |
| `test_unsupported_capability` | 无 V4 对应的能力返回错误 |
| `test_capability_exception` | 能力调用异常时返回错误而非抛出 |

### 6c. CompatConfig 测试

| 用例 | 描述 |
|------|------|
| `test_default_config` | 默认值正确 |
| `test_custom_config` | 自定义值正确 |

**验收条件**：
- [ ] 所有测试用例通过
- [ ] 测试覆盖 ComponentBridge 的 7 种组件映射和泛化调度
- [ ] 测试覆盖 CapabilityBridge 的核心能力路由

---

## T7：集成验证

**目标**：在 Docker 环境中验证兼容层可端到端运行。

**前置条件**：
- Docker 容器 `maim-bot-core` 运行中
- `data/MaiMBot/plugins/` 下有 V1 插件
- Docker 镜像包含 `maibot_sdk`（SDK v3）依赖

**验证步骤**：

1. 将兼容层插件复制到容器中
   ```bash
   docker cp plugins/maibot-team.v1-compat/ maim-bot-core:/MaiMBot/plugins/maibot-team.v1-compat/
   ```

2. 启动 MaiBot，观察日志：
   - 兼容层插件加载成功
   - V1 Runner 子进程启动成功
   - V1 插件组件注册到 ComponentBridge 内部路由表

3. 验证 V1 插件功能：
   - `v1.invoke_component` Tool 可通过 component_name 调用 V1 组件
   - `v1.component_event` Event 可接收 V1 事件
   - V1 插件的 `cap.call` 可路由到 V4 PluginContext

4. 验证异常场景：
   - V1 Runner 子进程崩溃后自动重启
   - 兼容层崩溃不影响其他 V4 插件

**验收条件**：
- [ ] 兼容层可加载至少 1 个 V1 插件
- [ ] `v1.invoke_component` 可端到端调用 V1 组件
- [ ] V1 插件的消息发送可端到端完成
- [ ] V1 Runner 子进程崩溃可自动重启
