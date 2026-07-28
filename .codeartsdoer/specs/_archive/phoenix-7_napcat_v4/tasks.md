# Phoenix-7：napcat-adapter v4 插件重写 — 编码任务

> 依赖：Phoenix-0~6 全部完成
> 核心交付：将 napcat-adapter 从 v1 内置插件重写为 v4 独立插件，通过 gRPC 双向流与 Host 通信
> 约束：不修改主程序代码（src/），插件代码位于 plugins/maibot-team.napcat-adapter/

---

## T1：项目骨架与配置

### T1.1：创建 v4 插件目录骨架

**操作**：在 `plugins/maibot-team.napcat-adapter/` 下重建 v4 目录结构

1. 保留可直接复用的模块（从 v1 复制到新结构中）：
   - `transport.py` — WS 客户端（100% 复用，仅调整 import）
   - `qq_emoji_list.py` — QQ 表情 ID 列表（100% 复用）
   - `constants.py` — 常量定义（100% 复用，移除 v1 专属常量）
   - `types.py` — 类型定义（100% 复用）
   - `filters.py` — 聊天名单/正则过滤（100% 复用，仅调整 import）
   - `heartbeat_monitor.py` — 心跳监控（100% 复用，仅调整 import）
   - `services/` — query_service、action_service、official_bot_guard、ban_tracker、ban_state_store（100% 复用，仅调整 import）
   - `codecs/inbound/text.py` — CQ 码/文本处理（100% 复用）
   - `codecs/inbound/cards.py` — 卡片消息处理（100% 复用）
   - `codecs/outbound/segment_encoder.py` — 出站消息段编码（100% 复用）

2. 新建 v4 独有模块（空文件，后续任务填充）：
   - `session_mapper.py`
   - `dedup.py`
   - `event_buffer.py`
   - `config.py`（v4 配置模型）

3. 删除 v1 架构模块（不再需要）：
   - `runtime/` 目录（router.py、builder.py、bundle.py）
   - `apis/` 目录
   - `_manifest.json`（v2 格式，替换为 manifest.json v3）

4. 重写入口文件：
   - `__init__.py` — `create_plugin()` 返回 v4 NapCatAdapterPlugin
   - `plugin.py` — v4 主类骨架

**验证**：`python -c "from plugins.maibot_team.napcat_adapter import create_plugin"` 不报错（此时插件可导入但无功能）

### T1.2：编写 Manifest v3

**文件**：`plugins/maibot-team.napcat-adapter/manifest.json`

按 design.md 2.4.1 编写 manifest.json：
- `manifest_version: 3`
- `id: "maibot-team.napcat-adapter"`
- `version: "2.0.0"`
- `sdk.min_version: "4.0.0"`
- `scopes`: 9 个 scope（message:send:text/image/emoji/forward/hybrid、session:read:detail、database:read:self、database:write:self、system:execute:command）

**验证**：`python -c "from src.plugin_runtime_v2.sdk.manifest import ManifestV3; import json; m = ManifestV3.model_validate(json.load(open('plugins/maibot-team.napcat-adapter/manifest.json'))); print(m.id, len(m.scopes))"` 输出 `maibot-team.napcat-adapter 9`

### T1.3：编写 v4 配置模型

**文件**：`plugins/maibot-team.napcat-adapter/config.py`

替换 v1 的 `PluginConfigBase + pydantic` 方案，改为简单 dataclass + TOML 读取：

1. `NapCatServerConfig`：ws_url、http_url、access_token、connection_id、action_timeout_sec、heartbeat_interval_sec、reconnect_delay_sec
2. `NapCatReconnectConfig`：max_retries、interval_sec
3. `NapCatBufferConfig`：event_buffer_size
4. `NapCatChatConfig`：enable_chat_list_filter、group_list、private_list、ban_qq_bot、ignore_self_message
5. `NapCatFilterConfig`：regex_filter_enabled、regex_filter_mode、regex_filter_patterns
6. `NapCatPluginSettings`：聚合以上配置，提供 `should_connect()`、`validate_runtime_config()` 方法

**关键差异**：v1 用 `PluginConfigBase`（依赖 maibot_sdk v1），v4 不依赖 v1 SDK，改用纯 dataclass + `tomllib`（Python 3.11+）或 `tomli` 读取 config.toml。

**验证**：`python -c "from plugins.maibot_team.napcat_adapter.config import NapCatPluginSettings; s = NapCatPluginSettings(); print(s.should_connect())"` 不报错

### T1.4：编写 config.toml

**文件**：`plugins/maibot-team.napcat-adapter/config.toml`

按 design.md 2.4.2 编写默认配置文件，包含 `[napcat_server]`、`[reconnect]`、`[buffer]`、`[chat]`、`[filters]` 五个 section。

**验证**：`python -c "import tomllib; tomllib.load(open('plugins/maibot-team.napcat-adapter/config.toml', 'rb'))"` 不报错

---

## T2：传输层迁移

### T2.1：迁移 NapCatTransportClient

**文件**：`plugins/maibot-team.napcat-adapter/transport.py`

从 v1 复制 `NapCatTransportClient`，调整：
1. import 路径：`from .config import NapCatServerConfig` 保持不变（同目录）
2. 移除对 v1 SDK 的任何依赖
3. 保持接口契约不变：`configure(server_config)` → `start()` → `stop()` → `call_action(action_name, params) → response_dict`
4. 保持回调机制：`on_connection_opened`、`on_connection_closed`、`on_payload`

**验证**：`python -c "from plugins.maibot_team.napcat_adapter.transport import NapCatTransportClient; print(NapCatTransportClient.is_available())"` 输出 `True`（需 aiohttp 已安装）

---

## T3：辅助模块

### T3.1：实现 SessionIdMapper

**文件**：`plugins/maibot-team.napcat-adapter/session_mapper.py`

按 design.md 2.3.2 实现 session_id 双向映射：

1. `calculate_session_id(platform, user_id, group_id, account_id, scope) → str` — 复制 `SessionUtils.calculate_session_id()` 算法（MD5 哈希，群聊 key = `platform[_account:xxx][_scope:xxx]_{group_id}`，私聊 key = `platform[_account:xxx][_scope:xxx]_{user_id}_private`）
2. `register_session(session_id, group_id, user_id) → None` — 建立双向映射（内存 dict）
3. `resolve_qq_ids(session_id) → tuple[str, str]` — 返回 `(group_id, user_id)`，未命中返回 `("", "")`
4. `persist(storage_ctx) → async None` — 通过 `ctx.storage` 持久化映射到 key `sid_map:forward` / `sid_map:reverse`
5. `restore(storage_ctx) → async None` — 从 `ctx.storage` 恢复映射

**关键**：`calculate_session_id` 必须与 `src/common/utils/utils_session.py` 的算法完全一致，否则 session_id 不匹配。

**验证**：
```python
from plugins.maibot_team.napcat_adapter.session_mapper import SessionIdMapper
m = SessionIdMapper()
sid = m.calculate_session_id("qq", user_id="12345")
sid2 = m.calculate_session_id("qq", group_id="67890")
m.register_session(sid, "", "12345")
m.register_session(sid2, "67890", "")
assert m.resolve_qq_ids(sid) == ("", "12345")
assert m.resolve_qq_ids(sid2) == ("67890", "")
```

### T3.2：实现 MessageDeduplicator

**文件**：`plugins/maibot-team.napcat-adapter/dedup.py`

按 design.md 2.3.2 实现消息去重：

1. `is_duplicate(message_id) → bool` — 检查是否已见过
2. `record(message_id) → None` — 记录 message_id + timestamp
3. `cleanup() → None` — 惰性清理过期条目（TTL 300s）
4. 内部使用 `OrderedDict[str, float]`，最多 1000 条（LRU 淘汰）

**验证**：
```python
from plugins.maibot_team.napcat_adapter.dedup import MessageDeduplicator
d = MessageDeduplicator()
assert not d.is_duplicate("msg1")
d.record("msg1")
assert d.is_duplicate("msg1")
assert not d.is_duplicate("msg2")
```

### T3.3：实现 EventBuffer

**文件**：`plugins/maibot-team.napcat-adapter/event_buffer.py`

按 design.md 2.3.2 实现 gRPC 断连事件缓存：

1. `push(event_name, payload) → bool` — 队列满时丢弃最旧事件，返回是否成功入队
2. `flush(ctx) → async int` — 逐条 `ctx.emit_event()` 重放，失败时保留未重放部分不丢弃，返回成功重放事件数
3. `clear() → None` — 清空缓存
4. `size() → int` — 当前缓存条数
5. 内部使用 `asyncio.Queue`，上限由配置决定（默认 1000），硬上限 5000
6. 记录 `_dropped_count` 统计丢弃事件数

**验证**：
```python
from plugins.maibot_team.napcat_adapter.event_buffer import EventBuffer
b = EventBuffer(max_size=10)
assert b.push("test.event", {"key": "val"})
assert b.size() == 1
b.clear()
assert b.size() == 0
```

---

## T4：入站消息编解码

### T4.1：迁移入站消息段解析

**文件**：`plugins/maibot-team.napcat-adapter/codecs/inbound/text.py`、`cards.py`

从 v1 直接复制，调整 import 路径。这两个 Mixin 不涉及输出格式，100% 可复用。

**验证**：`python -c "from plugins.maibot_team.napcat_adapter.codecs.inbound.text import NapCatInboundTextMixin; print('ok')"` 不报错

### T4.2：重写入站消息编解码器

**文件**：`plugins/maibot-team.napcat-adapter/codecs/inbound/message_codec.py`

基于 v1 的 `NapCatInboundCodec` 重写，核心变更是输出格式从 `MessageDict` 转为 v4 Event payload：

1. 保留 `convert_segments_with_metadata()` 方法（消息段解析逻辑不变）
2. 保留 `build_plain_text()` 方法（纯文本提取逻辑不变）
3. 新增 `build_event_payload(payload, self_id, sender_user_id, sender, session_id) → dict`：
   - 输出字段按 design.md 2.2.2 `napcat.message` / `napcat.group_message` Event payload 定义
   - 包含：session_id、platform="qq"、sender_id、sender_name、plain_text、message_segments（JSON 字符串）、message_id、is_notify=False、additional_config（JSON 字符串）
   - 群聊时 additional_config 包含 group_id
4. 移除 `build_message_dict()` 方法（v1 MessageDict 格式不再使用）

**验证**：
```python
# 构造模拟 payload，调用 build_event_payload，验证输出字段完整
from plugins.maibot_team.napcat_adapter.codecs.inbound.message_codec import NapCatInboundCodec
codec = NapCatInboundCodec(logger=..., query_service=...)
# payload = {"message_type": "private", "message": [...], ...}
# result = await codec.build_event_payload(payload, "self_id", "user_id", {}, "session_id")
# assert result["platform"] == "qq"
# assert result["is_notify"] is False
```

### T4.3：重写入站通知编解码器

**文件**：`plugins/maibot-team.napcat-adapter/codecs/notice/message_codec.py`、`enricher.py`、`helpers.py`、`renderer.py`、`meta_event_logger.py`

基于 v1 重写，核心变更是输出格式从 `MessageDict` 转为 v4 Event payload：

1. 保留 `NapCatNoticeEntityResolver`（enricher.py，查询用户/群信息）
2. 保留 `NapCatNoticeTextRenderer`（renderer.py，生成通知文本）
3. 保留 `NapCatMetaEventObserver`（meta_event_logger.py，元事件日志）
4. 保留辅助函数（helpers.py）
5. 新增 `build_notice_event_payload(payload, session_id) → dict`：
   - 输出字段按 design.md 2.2.2 `napcat.notice` Event payload 定义
   - 包含：session_id、platform="qq"、is_notify=True、napcat_notice_type、napcat_notice_sub_type、napcat_notice_payload（完整 JSON 字符串）、sender_id、group_id
   - 未知通知类型不丢弃，napcat_notice_sub_type 设为 "unknown"
6. 移除 `build_notice_message_dict()` 方法

**验证**：构造模拟通知 payload，调用 `build_notice_event_payload`，验证输出包含 napcat_notice_type 和 napcat_notice_sub_type 字段

---

## T5：出站消息编解码

### T5.1：迁移出站消息段编码器

**文件**：`plugins/maibot-team.napcat-adapter/codecs/outbound/segment_encoder.py`

从 v1 直接复制，调整 import 路径。此模块将 MaiMessage 格式转为 OneBot 11 消息段，逻辑不变。

**验证**：`python -c "from plugins.maibot_team.napcat_adapter.codecs.outbound.segment_encoder import NapCatOutboundSegmentEncoder; print('ok')"` 不报错

### T5.2：重写出站消息编解码器

**文件**：`plugins/maibot-team.napcat-adapter/codecs/outbound/message_codec.py`

基于 v1 的 `NapCatOutboundCodec` 重写，核心变更是输入格式从 `MessageDict + route` 转为 Tool args + SessionIdMapper：

1. 新增 `build_send_text_action(session_id, text, reply_to, at_user_id, sid_mapper) → (action_name, params)`：
   - 通过 `sid_mapper.resolve_qq_ids(session_id)` 获取 group_id/user_id
   - 构造 OneBot 11 send_msg / send_group_msg / send_private_msg action
   - 包含 reply 段（如有 reply_to）和 at 段（如有 at_user_id）

2. 新增 `build_send_image_action(session_id, image_base64, reply_to, sid_mapper) → (action_name, params)`

3. 新增 `build_send_emoji_action(session_id, emoji_base64, sid_mapper) → (action_name, params)`

4. 新增 `build_send_forward_action(session_id, forward_message_id, sid_mapper) → (action_name, params)`

5. 新增 `build_send_hybrid_action(session_id, hybrid_payload, reply_to, at_user_id, sid_mapper) → (action_name, params)`

6. 保留 `NapCatOutboundSegmentEncoder` 用于消息段构造

7. 移除 `build_outbound_action(message, route)` 方法（v1 接口不再使用）

**验证**：
```python
from plugins.maibot_team.napcat_adapter.codecs.outbound.message_codec import NapCatOutboundCodec
codec = NapCatOutboundCodec()
# 注册 session_id 映射后，调用 build_send_text_action
# 验证返回的 action_name 和 params 正确
```

---

## T6：过滤与路由

### T6.1：迁移聊天名单过滤与正则过滤

**文件**：`plugins/maibot-team.napcat-adapter/filters.py`

从 v1 直接复制，调整 import 路径（`from .config import NapCatChatConfig, NapCatFilterConfig`）。

**验证**：`python -c "from plugins.maibot_team.napcat_adapter.filters import NapCatRegexFilter; print('ok')"` 不报错

### T6.2：迁移心跳监控

**文件**：`plugins/maibot-team.napcat-adapter/heartbeat_monitor.py`

从 v1 直接复制，无 import 调整需求（仅依赖 asyncio 和 typing）。

**验证**：`python -c "from plugins.maibot_team.napcat_adapter.heartbeat_monitor import NapCatHeartbeatMonitor; print('ok')"` 不报错

### T6.3：迁移服务层

**文件**：`plugins/maibot-team.napcat-adapter/services/`

从 v1 直接复制整个 services/ 目录，调整 import 路径：
- `query_service.py` — QQ 查询服务
- `action_service.py` — QQ 动作服务
- `official_bot_guard.py` — 官方机器人屏蔽
- `ban_tracker.py` — 禁言追踪
- `ban_state_store.py` — 禁言状态存储

**验证**：`python -c "from plugins.maibot_team.napcat_adapter.services import NapCatQueryService; print('ok')"` 不报错

---

## T7：插件主类

### T7.1：实现 NapCatAdapterPlugin 主类

**文件**：`plugins/maibot-team.napcat-adapter/plugin.py`

这是核心任务，将 v1 的 `NapCatAdapterPlugin + Mixin + @MessageGateway` 架构重写为 v4 的 `MaiBotPlugin + @Tool/@Event` 架构：

1. **类定义**：
   - 继承 `src.plugin_runtime_v2.sdk.plugin.MaiBotPlugin`
   - `plugin_id = "maibot-team.napcat-adapter"`
   - `plugin_version = "2.0.0"`
   - `scopes = [9 个 scope]`

2. **@Event 声明**（3 个）：
   - `napcat.message` — 私聊消息事件
   - `napcat.group_message` — 群聊消息事件
   - `napcat.notice` — 通知事件

3. **@Tool 声明**（5 个）：
   - `napcat.send_text` — 发送文本消息
   - `napcat.send_image` — 发送图片消息
   - `napcat.send_emoji` — 发送表情包
   - `napcat.send_forward` — 发送转发消息
   - `napcat.send_hybrid` — 发送图文混合消息

4. **生命周期方法**：
   - `on_load()`：加载配置 → 初始化 SessionIdMapper → 恢复持久化映射 → 初始化 TransportClient → 启动 WS 连接
   - `on_unload()`：停止 WS 连接 → 持久化 SessionIdMapper → 清理资源
   - `on_config_update(config)`：解析新配置 → 重启连接

5. **入站处理流程**（替代 v1 的 NapCatEventRouter）：
   - `_handle_transport_payload(payload)` — post_type 分发
   - `_handle_inbound_message(payload)` — 自身消息过滤 → 聊天名单过滤 → 官方机器人屏蔽 → 去重检查 → 入站编解码 → `_emit_or_buffer()`
   - `_handle_notice_event(payload)` — 聊天名单过滤 → 通知编解码 → `_emit_or_buffer()`
   - `_handle_meta_event(payload)` — 心跳更新 / 生命周期日志

6. **出站处理流程**（替代 v1 的 @MessageGateway）：
   - `_send_message_common(args, build_action_fn)` — session_id 反解 → 构造 OneBot action → call_action → 返回结果
   - 5 个 Tool handler 调用 `_send_message_common`，传入对应的 `build_action_fn`

7. **gRPC 断连处理**：
   - `_emit_or_buffer(event_name, payload)` — 检查 `self.ctx._runner.is_ready`，就绪则 `ctx.emit_event()`，否则 `EventBuffer.push()`
   - gRPC 重连后调用 `EventBuffer.flush(ctx)`

**验证**：
```python
from plugins.maibot_team.napcat_adapter.plugin import NapCatAdapterPlugin
p = NapCatAdapterPlugin()
assert p.plugin_id == "maibot-team.napcat-adapter"
# 检查 @Tool/@Event 声明
tools = [attr for attr in dir(p) if not attr.startswith('_') and hasattr(getattr(p, attr), '_mcp_tool')]
events = [attr for attr in dir(p) if not attr.startswith('_') and hasattr(getattr(p, attr), '_mcp_event')]
assert len(tools) == 5
assert len(events) == 3
```

### T7.2：实现 __init__.py 入口

**文件**：`plugins/maibot-team.napcat-adapter/__init__.py`

```python
"""NapCat v4 适配器插件包。"""
from .plugin import NapCatAdapterPlugin

def create_plugin() -> NapCatAdapterPlugin:
    return NapCatAdapterPlugin()
```

**验证**：`python -c "from plugins.maibot_team.napcat_adapter import create_plugin; p = create_plugin(); print(p.plugin_id)"` 输出 `maibot-team.napcat-adapter`

---

## T8：集成验证

### T8.1：插件加载验证

**操作**：验证 napcat-adapter v4 可被 Host 加载

1. 确保 manifest.json 格式正确（ManifestV3 校验通过）
2. 确保 `create_plugin()` 返回的实例有正确的 @Tool/@Event 声明
3. 确保 PluginLoader 能正确扫描并收集所有声明

**验证**：
```python
from src.plugin_runtime_v2.runner.plugin_loader import PluginLoader
from plugins.maibot_team.napcat_adapter.plugin import NapCatAdapterPlugin
loader = PluginLoader(NapCatAdapterPlugin)
tools, events, cards, instance = await loader.load()
assert len(tools) == 5  # send_text, send_image, send_emoji, send_forward, send_hybrid
assert len(events) == 3  # napcat.message, napcat.group_message, napcat.notice
assert instance is not None
```

### T8.2：入站消息流验证

**操作**：验证从 NapCatQQ WS 事件到 Event 推送的完整链路

1. 构造模拟 OneBot 11 私聊消息 payload
2. 调用 `_handle_inbound_message(payload)`
3. 验证生成的 Event payload 字段完整（session_id、platform、sender_id、plain_text 等）

4. 构造模拟 OneBot 11 群聊消息 payload
5. 验证 Event payload 包含 group_id

6. 构造模拟通知事件 payload
7. 调用 `_handle_notice_event(payload)`
8. 验证 Event payload 包含 napcat_notice_type 和 napcat_notice_sub_type

**验证**：手动构造 payload 并调用处理方法，检查输出 Event payload 字段与 design.md 2.2.2 定义一致

### T8.3：出站消息流验证

**操作**：验证从 Tool 调用到 NapCatQQ HTTP API 的完整链路

1. 注册 session_id 映射（SessionIdMapper.register_session）
2. 构造 Tool 调用参数（session_id + text）
3. 调用 `send_text(args)`
4. 验证生成的 OneBot action 名称和参数正确

5. 同理验证 send_image、send_emoji、send_forward、send_hybrid

**验证**：mock `transport.call_action()`，验证传入的 action_name 和 params 符合 OneBot 11 规范

### T8.4：异常场景验证

**操作**：验证关键异常场景的处理

1. **session_id 无法映射**：调用 send_text 传入未注册的 session_id → 返回 `{"success": False, "error": "SESSION_NOT_FOUND"}`
2. **NapCatQQ API 调用失败**：mock call_action 抛出异常 → Tool 返回 `{"success": False, "error": "API_ERROR"}`
3. **gRPC 断连事件缓存**：mock `ctx._runner.is_ready = False` → 事件入 EventBuffer → 恢复后 flush
4. **消息去重**：连续两次处理同一 message_id → 第二次被过滤
5. **自身消息过滤**：sender_user_id == self_id → 不推送 Event

**验证**：每个异常场景都有明确的错误返回或正确的降级行为

### T8.5：session_id 算法一致性验证

**操作**：验证插件的 `SessionIdMapper.calculate_session_id()` 与主程序 `SessionUtils.calculate_session_id()` 输出完全一致

```python
from src.common.utils.utils_session import SessionUtils
from plugins.maibot_team.napcat_adapter.session_mapper import SessionIdMapper

mapper = SessionIdMapper()

# 私聊
assert mapper.calculate_session_id("qq", user_id="12345") == SessionUtils.calculate_session_id("qq", user_id="12345")
# 群聊
assert mapper.calculate_session_id("qq", group_id="67890") == SessionUtils.calculate_session_id("qq", group_id="67890")
# 带 account_id
assert mapper.calculate_session_id("qq", user_id="12345", account_id="bot1") == SessionUtils.calculate_session_id("qq", user_id="12345", account_id="bot1")
# 带 scope
assert mapper.calculate_session_id("qq", group_id="67890", scope="test") == SessionUtils.calculate_session_id("qq", group_id="67890", scope="test")
```

**验证**：所有断言通过，session_id 算法 100% 一致

**回归测试**：在 `tests/plugin_runtime_v2/` 下新增 `test_session_id_consistency.py`，对比 SessionIdMapper.calculate_session_id() 与 SessionUtils.calculate_session_id() 的输出，确保算法同步。主程序算法变更时此测试会报错。

---

## 任务依赖与执行顺序

```
T1 (骨架/配置) ──→ T2 (传输层) ──→ T7 (插件主类) ──→ T8 (集成验证)
       │                                      ↑
       ├──→ T3 (辅助模块) ────────────────────┤
       ├──→ T4 (入站编解码) ─────────────────┤
       ├──→ T5 (出站编解码) ─────────────────┤
       └──→ T6 (过滤/路由) ──────────────────┘
```

推荐执行顺序：**T1 → T2 → T3 → T4 → T5 → T6 → T7 → T8**

T1 是所有任务的前置条件。T2~T6 可部分并行（T3/T4/T5/T6 之间无依赖），但建议串行执行以降低风险。T7 依赖所有前置模块。T8 是最终集成验证。

## 派发建议

| 任务 | 负责人 | 理由 |
|------|--------|------|
| T1.1 目录骨架 | Codex | 机械操作：复制文件、调整 import、删除旧文件 |
| T1.2 Manifest v3 | Codex | 格式明确，机械编写 |
| T1.3 配置模型 | CC | 需理解 v1→v4 配置架构差异，设计 dataclass 结构 |
| T1.4 config.toml | Codex | 格式明确，机械编写 |
| T2.1 传输层迁移 | Codex | 100% 复用，仅调整 import |
| T3.1 SessionIdMapper | CC | 核心模块，需确保算法与主程序一致 |
| T3.2 MessageDeduplicator | Codex | 独立模块，接口明确 |
| T3.3 EventBuffer | Codex | 独立模块，接口明确 |
| T4.1 入站消息段迁移 | Codex | 100% 复用，仅调整 import |
| T4.2 入站消息编解码 | CC | 核心变更：MessageDict → Event payload，需理解字段映射 |
| T4.3 入站通知编解码 | CC | 同上，通知事件格式变更 |
| T5.1 出站消息段迁移 | Codex | 100% 复用，仅调整 import |
| T5.2 出站消息编解码 | CC | 核心变更：MessageDict+route → Tool args+SessionIdMapper |
| T6.1-T6.3 过滤/服务迁移 | Codex | 100% 复用，仅调整 import |
| T7.1 插件主类 | CC | 核心任务：需理解 v1→v4 架构全貌，设计 @Tool/@Event 声明和事件流 |
| T7.2 入口文件 | Codex | 简单 |
| T8.1-T8.5 集成验证 | CC | 需理解完整链路，验证功能对等 |