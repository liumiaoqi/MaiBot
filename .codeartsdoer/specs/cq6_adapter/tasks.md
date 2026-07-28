# CQ-6 Tasks: napcat-adapter 插件化迁移 + v2 EventDispatcher 闭环

## 依赖关系

```
T0 → T1 → T2 → T3 → T4
                ↘
T5 ──────────────→ T6 → T7
```

T0 是前置修复，T1~T4 是核心闭环链，T5~T7 是配置/验证。

---

## T0: inbound_codec 运行时错误修复

**对应需求**: R1 前置条件
**对应设计**: AD-0
**负责人**: CC
**预估**: 1h

- [ ] 修复 `plugins/maibot-team.napcat-adapter/codecs/inbound/message_codec.py` 中 `convert_segments_with_metadata()` 未定义问题：
  - 检查 `NapCatInboundCardMixin` / `NapCatInboundTextMixin` 是否有 `convert_segments()` 等替代方法
  - 如无，实现 `convert_segments_with_metadata()` 或改用已有方法
- [ ] 修复 TypedDict 无 `to_dict()` 问题：`[s.to_dict() for s in segments]` 改为 `[dict(s) for s in segments]` 或直接 `list(segments)`
- [ ] 验证：napcat-adapter 能正常解析 OneBot 11 消息并生成 event payload

**验证**: inbound_codec 对示例 OneBot 11 payload 不抛 AttributeError

---

## T1: napcat-adapter @Event 声明补全

**对应需求**: R2
**对应设计**: AD-4, M4
**负责人**: CC/Codex
**预估**: 30min

- [ ] 在 `plugins/maibot-team.napcat-adapter/plugin.py` 的 `NapCatAdapterPlugin` 类上添加 3 个 @Event 装饰器方法：
  - `_on_private_message` → `napcat.message`
  - `_on_group_message` → `napcat.group_message`
  - `_on_notice` → `napcat.notice`
- [ ] 每个 @Event 声明 `name`、`description`、`event_schema`
- [ ] 在 `manifest.json` 的 scopes 中添加 `message:receive:private`、`message:receive:group`、`message:receive:notice`

**验证**: PluginLoader 扫描后 `_event_declarations` 包含 3 个 napcat 事件

---

## T2: NapCatPayloadConverter 新建

**对应需求**: R1
**对应设计**: AD-2, M2
**负责人**: CC
**预估**: 1h

- [ ] 新建 `src/plugin_runtime_v2/mcp/payload_converter.py`
- [ ] 实现 `NapCatPayloadConverter` 类：
  - `convert(payload: dict, event_name: str) -> SessionMessage`
  - 私聊 payload 映射（见 design.md AD-2 字段映射表）
  - 群聊 payload 映射（含 group_info 构造）
  - 通知 payload 映射（`is_notify=True`）
  - segments → MessageSequence 转换（复用 v1 `_message_sequence_from_dict` 逻辑）
  - `is_mentioned` 从 segments 中检测 at 段
- [ ] 单元测试：覆盖 3 种 payload（私聊/群聊/通知），验证 SessionMessage 各字段正确

**验证**: `pytest tests/test_payload_converter.py` 通过

---

## T3: EventDispatcher 闭环

**对应需求**: R1
**对应设计**: AD-1, AD-3, M1
**负责人**: CC
**预估**: 1h

- [ ] 修改 `EventDispatcher.__init__`：
  - 参数改为 `get_message_port: Callable[[], MessageIngestionPort]` + `get_session_repo: Callable[[], SessionRepository] | None = None`
  - 删除旧的 `message_port`/`session_repo`/`person_info_port` 可选参数
  - 新增 `_payload_converter = NapCatPayloadConverter()` 属性
- [ ] 修改 `dispatch()`：
  - 对 `napcat.message` / `napcat.group_message` / `napcat.notice`：
    - `session_message = self._payload_converter.convert(payload, event_name)`
    - `await self._get_message_port().receive_message(session_message)`
  - 对有 `card_metadata` 的 Event：保持日志（TODO: Phoenix-4）
  - 对其他 Event：保持日志
- [ ] 单元测试：mock `get_message_port`，验证 dispatch 对 napcat 事件调用 `receive_message`

**验证**: `pytest tests/test_event_dispatcher.py` 通过

---

## T4: Bootstrap Port 注入

**对应需求**: R1
**对应设计**: AD-3, M3
**负责人**: Codex
**预估**: 15min

- [ ] 修改 `src/plugin_runtime_v2/mcp/bootstrap.py`：
  - 导入 `from src.core.adapters.message_ingestion_port import get_message_ingestion_port`
  - `EventDispatcher()` → `EventDispatcher(get_message_port=get_message_ingestion_port)`

**验证**: MaiBot 启动无 ImportError，EventDispatcher 持有有效 Port 获取函数

---

## T5: Runner entrypoint 插件加载

**对应需求**: R3
**对应设计**: AD-5, M5
**负责人**: CC
**预估**: 1h

- [ ] 修改 `src/plugin_runtime_v2/runner/entrypoint.py`：
  - 在 `_run()` 中添加插件发现逻辑：扫描 `args.plugin_dir` → 读取 `manifest.json` → 动态导入 `plugin.py` → 调用 `create_plugin()`
  - 注入 `PluginContext`（从 `RunnerEndpoint` 获取）
  - 调用 `plugin.on_load()`
  - 优雅关闭：`on_unload()` on SIGTERM/SIGINT
- [ ] 验证：Runner 启动后日志显示插件加载成功

**验证**: Runner 进程启动后加载 napcat-adapter，日志显示 `on_load` 调用

---

## T6: v2 默认启用

**对应需求**: R4
**对应设计**: AD-6, M6
**负责人**: Codex
**预估**: 5min

- [ ] 修改 `src/config/official_configs.py`：`PluginRuntimeV2Config.enabled` 默认值 `False` → `True`

**验证**: 新安装时 v2 默认启用

---

## T7: 端到端验证

**对应需求**: R5
**对应设计**: —
**负责人**: CA（Docker 验证）
**预估**: 30min

- [ ] 重启 `maim-bot-core` 容器
- [ ] 检查日志：v2 HostEndpoint 启动成功
- [ ] 检查日志：napcat-adapter 加载成功、@Event 声明收集到 3 个
- [ ] 通过 NapCat WebUI 发送测试消息
- [ ] 检查 MaiBot 日志：`receive_message()` 被调用，SessionMessage 字段正确
- [ ] 验证核心管道正常处理消息（智能体思考 → 回复）

**验证**: QQ 消息能从 NapCat WS 入站到 MaiBot 核心管道，智能体正常回复