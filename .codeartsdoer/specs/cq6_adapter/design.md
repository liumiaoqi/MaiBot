# CQ-6 Design: napcat-adapter 插件化迁移 + v2 EventDispatcher 闭环

## 架构决策

### AD-1: EventDispatcher 消息路由策略

**决策**：EventDispatcher.dispatch() 对 `napcat.message` / `napcat.group_message` 事件，将 payload 转换为 SessionMessage 后调用 `MessageIngestionPort.receive_message()`。

**理由**：v1 MessageGateway 已有完整 payload→SessionMessage 转换逻辑（`_build_session_message_from_dict`），v2 复用同一转换路径。EventDispatcher 是 v2 消息入站的唯一汇聚点，在此处做转换最自然。

**替代方案**：
- 在 MCPHostBridge.on_event_received() 中转换 → 违反单一职责，Bridge 只做路由
- 在 napcat-adapter 内部直接调用 Port → 违反插件隔离，插件不应直接导入核心 Port

### AD-0: inbound_codec 运行时错误修复（前置条件）

**问题**：napcat-adapter `inbound_codec` 当前有两处运行时错误，不可执行：
1. `convert_segments_with_metadata()` 方法未定义（`NapCatInboundCardMixin` + `NapCatInboundTextMixin` 均无此方法）
2. `NapCatHostMessageSegment` 是 TypedDict，没有 `to_dict()` 方法

**决策**：在实现 PayloadConverter 之前，先修复 inbound_codec 使其可运行。具体方案：
- 实现 `convert_segments_with_metadata()` 方法（或改用已有的 `convert_segments()` 如果存在）
- TypedDict 实例本身就是 dict，`[s.to_dict() for s in segments]` 改为 `[dict(s) for s in segments]` 或直接 `list(segments)`

**优先级**：这是 CQ-6 的前置阻塞项，必须在 T2 之前修复。

### AD-2: Event payload → SessionMessage 转换器

**决策**：新建 `NapCatPayloadConverter` 类，放在 `src/plugin_runtime_v2/mcp/` 下，将 napcat Event payload dict 转为 SessionMessage。

**理由**：
- napcat Event payload 字段（`qq_user_id`、`qq_group_id`、`sender_name`、`segments`）与 v1 MessageDict 字段（`message_info.user_info.user_id`）结构不同，不能直接复用 `_build_session_message_from_dict`
- 但 SessionMessage 构造逻辑相同，只是字段映射不同
- 独立转换器便于测试和维护

**字段映射**：

| SessionMessage 字段 | napcat Event payload 来源 | 说明 |
|---------------------|--------------------------|------|
| `message_id` | `payload["message_id"]` | 必需 |
| `timestamp` | `payload["timestamp"]` → `datetime.fromtimestamp()` | Unix 时间戳 |
| `platform` | `"qq"` | 固定值 |
| `message_info.user_info.user_id` | `payload["qq_user_id"]` | |
| `message_info.user_info.user_nickname` | `payload["sender_name"]` | |
| `message_info.user_info.user_cardname` | `None` | v4 Event 无此字段 |
| `message_info.group_info` | `payload["qq_group_id"]` 非空时构造 | group_id + group_name |
| `message_info.additional_config` | `{}` | |
| `raw_message` | `payload["segments"]` → MessageSequence | 需从 segment dict 列表重建 |
| `is_mentioned` | 从 segments 检测 at 段 | |
| `session_id` | `payload["session_id"]` | |
| `is_notify` | `False`（消息事件） | |

### AD-3: Port 注入时序

**决策**：EventDispatcher 持有 Port 的**延迟获取函数**（`Callable[[], MessageIngestionPort]`），dispatch 时解析。

**理由**：
- bootstrap 创建 EventDispatcher 时，`MessageIngestionPort` 可能尚未注册（`set_message_ingestion_port()` 在 `_init_message_ingestion_port()` 中执行）
- 延迟获取避免时序依赖，与 `get_message_ingestion_port()` 模式一致

**实现**：
```python
class EventDispatcher:
    def __init__(
        self,
        get_message_port: Callable[[], MessageIngestionPort],
        get_session_repo: Callable[[], SessionRepository] | None = None,
    ) -> None:
        self._get_message_port = get_message_port
        self._get_session_repo = get_session_repo
```

### AD-4: napcat-adapter @Event 声明

**决策**：在 NapCatAdapterPlugin 类上添加 3 个 @Event 装饰器方法。

**实现**：
```python
@Event(name="napcat.message", description="QQ 私聊消息入站",
       event_schema={"type": "object", "properties": {
           "session_id": {"type": "string"},
           "message_id": {"type": "string"},
           "qq_user_id": {"type": "string"},
           "sender_name": {"type": "string"},
           "raw_message": {"type": "string"},
           "timestamp": {"type": "number"},
       }})
async def _on_private_message(self) -> None:
    """声明：QQ 私聊消息事件。"""
    pass

@Event(name="napcat.group_message", description="QQ 群聊消息入站",
       event_schema={"type": "object", "properties": {
           "session_id": {"type": "string"},
           "message_id": {"type": "string"},
           "qq_user_id": {"type": "string"},
           "qq_group_id": {"type": "string"},
           "sender_name": {"type": "string"},
           "raw_message": {"type": "string"},
           "timestamp": {"type": "number"},
           "is_group": {"type": "boolean"},
       }})
async def _on_group_message(self) -> None:
    """声明：QQ 群聊消息事件。"""
    pass

@Event(name="napcat.notice", description="QQ 通知事件（群成员变动等）",
       event_schema={"type": "object", "properties": {
           "napcat_notice_type": {"type": "string"},
           "napcat_sub_type": {"type": "string"},
           "qq_user_id": {"type": "string"},
           "qq_group_id": {"type": "string"},
       }})
async def _on_notice(self) -> None:
    """声明：QQ 通知事件。"""
    pass
```

### AD-5: v2 Runner 插件加载

**决策**：Runner entrypoint 从 `--plugin-dir` 发现并加载 MaiBotPlugin 子类，复用 v2 SDK 的 `PluginLoader` 逻辑。

**理由**：
- 当前 `--plugin-dir` 被解析但未使用（RunnerEndpointConfig 无 plugin_dir 字段）
- Phoenix 设计是 1 Runner = 1 Plugin，Runner 启动后需加载指定插件
- 加载逻辑：扫描 plugin-dir → 读取 manifest.json → 动态导入 plugin.py → 调用 create_plugin() → 注入 PluginContext → on_load()

**实现**：在 `_run()` 中添加插件发现和加载逻辑：
```python
async def _run(args: argparse.Namespace) -> None:
    config = RunnerEndpointConfig(...)
    endpoint = RunnerEndpoint(config)
    await endpoint.start()

    # 加载插件
    plugin = _load_plugin(args.plugin_dir)
    plugin.ctx = endpoint.get_plugin_context()
    await plugin.on_load()
```

### AD-6: v2 默认启用

**决策**：`PluginRuntimeV2Config.enabled` 默认值改为 `True`。

**理由**：v2 是 Phoenix 的核心交付，CQ-6 闭环后 v2 应成为默认路径。v1/v2 自然隔离（v1 不识别 manifest.json，v2 不识别 _manifest.json），不会重复加载。

### AD-7: napcat.notice 事件处理

**决策**：EventDispatcher 对 `napcat.notice` 事件，构造 `is_notify=True` 的 SessionMessage 后同样走 `MessageIngestionPort.receive_message()`。

**理由**：v1 路径中通知也进入主链路（`is_notify=True`，`notice_kind` 由核心判断）。保持行为一致。

## 修改清单

### M1: EventDispatcher 闭环
- **文件**: `src/plugin_runtime_v2/mcp/event_dispatcher.py`
- **改动**:
  1. `__init__` 改为接受 `get_message_port: Callable` + `get_session_repo: Callable | None`
  2. 新增 `_payload_converter: NapCatPayloadConverter` 属性
  3. `dispatch()` 对 `napcat.message` / `napcat.group_message` / `napcat.notice`：
     - 调用 `NapCatPayloadConverter.convert(payload, event_name)` → SessionMessage
     - 调用 `self._get_message_port().receive_message(session_message)`
  4. 对其他 Event 保持日志行为

### M2: NapCatPayloadConverter 新建
- **文件**: `src/plugin_runtime_v2/mcp/payload_converter.py`（新建）
- **职责**: napcat Event payload dict → SessionMessage
- **字段映射**: 见 AD-2
- **segments 转换**: 复用 v1 `PluginMessageUtils._message_sequence_from_dict()` 逻辑

### M3: Bootstrap Port 注入
- **文件**: `src/plugin_runtime_v2/mcp/bootstrap.py`
- **改动**:
  1. `EventDispatcher()` → `EventDispatcher(get_message_port=get_message_ingestion_port)`
  2. 导入 `get_message_ingestion_port`

### M4: napcat-adapter @Event 声明
- **文件**: `plugins/maibot-team.napcat-adapter/plugin.py`
- **改动**: 添加 3 个 @Event 装饰器方法（见 AD-4）

### M5: Runner entrypoint 插件加载
- **文件**: `src/plugin_runtime_v2/runner/entrypoint.py`
- **改动**: 在 `_run()` 中添加插件发现和加载逻辑（见 AD-5）

### M6: v2 默认启用
- **文件**: `src/config/official_configs.py`
- **改动**: `PluginRuntimeV2Config.enabled` 默认值 `False` → `True`

### M7: manifest scopes 补全
- **文件**: `plugins/maibot-team.napcat-adapter/manifest.json`
- **改动**: scopes 中添加 `message:receive:private`、`message:receive:group`、`message:receive:notice`

## 数据流（闭环后）

```
napcat WS → OneBot 11 payload
  → NapCatAdapterPlugin._handle_message_event()
    → inbound_codec.build_event_payload() → (event_name, event_payload)
    → ctx.emit_event(event_name, event_payload)
      → RunnerEndpoint.emit_event() → gRPC 双向流
        → HostServicer → MCPHostBridge.on_event_received()
          → _event_declarations[event_name] → (EventDeclaration, plugin_id)  ✅ 已声明
          → EventDispatcher.dispatch(event_name, payload, plugin_id, evt_decl)
            → NapCatPayloadConverter.convert(payload, event_name) → SessionMessage  ✅ 转换
            → get_message_ingestion_port().receive_message(session_message)  ✅ Port 注入
              → 核心消息处理管道  ✅
```

## 不做的事

1. **不修改 v1 运行时**：v1/v2 自然隔离，v1 不识别 manifest.json 不会加载 napcat-adapter
2. **不实现 ThinkingOrgan.think_proactive() 对接**：这是 CQ-7（欲望系统）的范畴，CQ-6 只闭环消息入站
3. **不实现 HomeCard WebUI 转发**：Phoenix-10 延后项
4. **不扩展 @Tool**：CQ-9x 扩展任务，不在 CQ-6 范围
5. **不修改 SessionMessage 数据模型**：只做字段映射，不改模型定义

## 测试策略

1. **单元测试**：`NapCatPayloadConverter.convert()` — 覆盖私聊/群聊/通知三种 payload
2. **单元测试**：`EventDispatcher.dispatch()` — mock Port，验证 receive_message 被调用
3. **集成测试**：模拟 gRPC Event 推送 → 验证 on_event_received → dispatch → receive_message 全链路
4. **端到端验证**（需 Docker）：NapCat WS 发送消息 → MaiBot 日志显示 receive_message 被调用