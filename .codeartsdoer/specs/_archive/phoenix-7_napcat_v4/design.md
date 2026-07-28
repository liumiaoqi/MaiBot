# Phoenix-7：napcat-adapter v4 插件重写 — 技术设计

# 一、需求与存量功能关系分析

## 1.1 需求功能与存量功能对比

### 1.1.1 已实现功能

| 需求功能 | 存量功能 | 代码位置 | 匹配度 |
|---------|---------|---------|--------|
| WebSocket 连接 NapCatQQ | NapCatTransportClient 正向 WS 连接循环 | `plugins/maibot-team.napcat-adapter/transport.py` | 100% |
| 私聊消息接收与解析 | NapCatInboundCodec.build_message_dict() | `plugins/maibot-team.napcat-adapter/codecs/inbound/message_codec.py` | 75% |
| 群聊消息接收与解析 | 同上，message_type=group 分支 | `plugins/maibot-team.napcat-adapter/codecs/inbound/message_codec.py` | 75% |
| 通知事件接收与解析 | NapCatNoticeCodec.build_notice_message_dict() | `plugins/maibot-team.napcat-adapter/codecs/notice/` | 75% |
| 消息段解析（text/image/at/reply/face/mface/record/file） | NapCatInboundCodec.convert_segments_with_metadata() | `plugins/maibot-team.napcat-adapter/codecs/inbound/message_codec.py` | 75% |
| CQ 码兼容解析 | NapCatInboundTextMixin | `plugins/maibot-team.napcat-adapter/codecs/inbound/text.py` | 100% |
| 自身消息过滤 | router.py: sender_user_id == self_id 判断 | `plugins/maibot-team.napcat-adapter/runtime/router.py:108` | 100% |
| 发送文本/图片/表情包/混合消息 | NapCatOutboundCodec.build_outbound_action() | `plugins/maibot-team.napcat-adapter/codecs/outbound/message_codec.py` | 75% |
| 消息 ID 回填（echo 机制） | handle_napcat_gateway 中 adapter_callbacks | `plugins/maibot-team.napcat-adapter/plugin.py:121-134` | 75% |
| NapCatQQ access_token 鉴权 | transport.py _build_headers() | `plugins/maibot-team.napcat-adapter/transport.py:329-338` | 100% |
| WebSocket 自动重连 | transport.py _connection_loop() | `plugins/maibot-team.napcat-adapter/transport.py:147-184` | 100% |
| 心跳监控 | NapCatHeartbeatMonitor | `plugins/maibot-team.napcat-adapter/heartbeat_monitor.py` | 100% |
| 聊天名单过滤 | NapCatChatFilter | `plugins/maibot-team.napcat-adapter/filters.py` | 100% |
| 官方机器人屏蔽 | NapCatOfficialBotGuard | `plugins/maibot-team.napcat-adapter/services/official_bot_guard.py` | 100% |
| 正则消息过滤 | NapCatRegexFilter | `plugins/maibot-team.napcat-adapter/filters.py` | 100% |
| 禁言状态追踪 | NapCatBanTracker | `plugins/maibot-team.napcat-adapter/services/ban_tracker.py` | 100% |
| session_id 计算 | SessionUtils.calculate_session_id() | `src/common/utils/utils_session.py:8-42` | 100% |

### 1.1.2 需要扩展的功能

| 需求功能 | 存量功能 | 差异说明 | 扩展方向 |
|---------|---------|---------|---------|
| v4 Event 推送（消息事件） | v1 ctx.gateway.route_message() 注入 Host | v1 通过 MessageGateway 能力注入；v4 需通过 ctx.emit_event() 推送 gRPC Event | 将 inbound_codec 输出从 MessageDict 转为 Event payload dict，调用 ctx.emit_event() |
| v4 Event 推送（通知事件） | v1 ctx.gateway.route_message() 注入 Host（is_notify=True） | 同上，通知事件也需转为 Event payload | 将 notice_codec 输出转为 napcat.notice Event payload |
| v4 Tool 声明（发送消息） | v1 @MessageGateway 装饰器 | v1 用 @MessageGateway 声明出站网关；v4 用 @Tool 声明拉取式工具 | 为每种消息类型声明 @Tool，handler 内调用 NapCatQQ HTTP API |
| Platform IO 注册 | v1 Supervisor 自动注册 PluginPlatformDriver | v1 通过 Supervisor.invoke_message_gateway() 桥接；v4 需新机制 | Host 侧 MCPHostBridge 需增强：收到 napcat.* Event 时自动注册 v4 PlatformIO 驱动 |
| 消息去重 | v1 通过 external_message_id + dedupe_key 由 PlatformIO 去重 | v4 Event 推送无内置去重；需插件自行去重 | 插件内维护近期 message_id 集合（LRU 缓存），重复事件跳过 |
| session_id 映射（出站） | v1 通过 PlatformIO route_metadata 传递 self_id/group_id | v4 Tool 参数只有 session_id，需反解为 QQ group_id/user_id | 插件内维护 session_id → QQ ID 映射表，使用 ctx.storage 持久化 |
| 消息 ID 映射持久化 | v1 通过 Host 侧 MessageUtils.update_message_id_async() | v4 插件独立进程，需自行持久化 ID 映射 | 使用 ctx.storage 存储映射关系，重启后恢复 |
| Manifest v3 格式 | v1 _manifest.json（manifest_version=2, capabilities=[]） | v3 格式需 scopes 字段、id 格式要求、sdk min_version=4.0.0 | 重写 manifest.json 为 v3 格式 |
| 配置管理 | v1 PluginConfigBase + config.toml | v4 SDK 暂无标准配置机制；需通过 on_config_update 接收 | 保留 config.toml，on_config_update 中重载连接 |
| gRPC 断连事件缓存 | v1 无此需求（与 Host 同进程） | v4 插件独立进程，gRPC 断连时需缓存入站事件 | 插件内维护 asyncio.Queue 缓存，gRPC 重连后重放 |

### 1.1.3 需要新增的功能或接口

**插件侧（plugins/maibot-team.napcat-adapter/）**：

1. **@Event 声明**：`napcat.message`、`napcat.group_message`、`napcat.notice` — v1 无对应，v4 需声明推送式组件
2. **@Tool 声明**：`napcat.send_text`、`napcat.send_image`、`napcat.send_emoji`、`napcat.send_forward`、`napcat.send_hybrid` — v1 用 @MessageGateway 统一出站，v4 需拆分为独立 Tool
3. **session_id 计算模块**：复制 SessionUtils.calculate_session_id() 算法到插件内，因为插件无法导入 src/ 模块
4. **session_id 反向映射**：从 session_id 反解 QQ group_id/user_id，v1 不需要（PlatformIO 传递 route_metadata）
5. **消息去重模块**：基于 message_id 的 LRU 去重缓存，v1 由 PlatformIO 去重
6. **gRPC 断连事件缓存**：内存队列 + 重放机制，v1 无此需求

**Host 侧（src/，P-5 集成范围）**：

1. **EventDispatcher 增强**：收到 `napcat.message`/`napcat.group_message` Event 时，构造 CoreMessage 并注入 ChatBot.message_process()
2. **EventDispatcher 通知路由**：收到 `napcat.notice` Event 时，构造通知消息并注入 ChatBot.handle_notice_message()
3. **v4 PlatformIO 驱动注册**：napcat-adapter 注册后，自动创建 v4 版 PluginPlatformDriver，出站时调用插件的 Tool
4. **消息 ID echo 回填**：napcat-adapter 通过 Event 推送 echo 信息，Host 侧更新 message_id 映射

## 1.2 存量功能详细分析

### 1.2.1 NapCatTransportClient（传输层）

- **接口契约**：`configure(server_config)` → `start()` → `stop()`；运行时 `call_action(action_name, params) → response_dict`
- **业务规则**：正向 WS 连接，echo 机制匹配请求-响应，自动重连（固定间隔），连接生命周期回调（on_connection_opened/closed/payload）
- **扩展点**：回调函数可替换；server_config 可动态更新
- **约束**：依赖 aiohttp；单连接模型（不支持多 WS 并行）；call_action 有超时限制

### 1.2.2 NapCatInboundCodec（入站编解码）

- **接口契约**：`build_message_dict(payload, self_id, sender_user_id, sender) → MessageDict`
- **业务规则**：消息段转换（text/image/at/reply/face/mface/record/file → MaiMessage 格式）；CQ 码兼容；群名片优先于昵称；@检测
- **扩展点**：NapCatInboundCardMixin（卡片消息）、NapCatInboundTextMixin（文本处理）可独立扩展
- **约束**：输出格式为 maim_message.MessageBase 兼容的 dict，v4 需转为 Event payload 格式

### 1.2.3 NapCatOutboundCodec（出站编解码）

- **接口契约**：`build_outbound_action(message_dict, route) → (action_name, params)`
- **业务规则**：根据消息类型构造 OneBot 11 action（send_msg/send_private_msg/send_group_msg）；图片/表情包 base64 → CQ 码或数组格式；回复消息构造 reply 段；@消息构造 at 段
- **约束**：输入为 MessageDict（v4 需从 Tool 参数转换）；NapCatQQ 对大图片有大小限制

### 1.2.4 NapCatEventRouter（事件路由）

- **接口契约**：`handle_transport_payload(payload)` → 分发到 `handle_inbound_message()`/`handle_notice_event()`/`handle_meta_event()`
- **业务规则**：post_type 分发；自身消息过滤；聊天名单过滤；官方机器人屏蔽；正则消息过滤
- **约束**：v1 通过 `ctx.gateway.route_message()` 注入 Host；v4 需改为 `ctx.emit_event()`

### 1.2.5 SessionUtils.calculate_session_id（session_id 计算）

- **接口契约**：`calculate_session_id(platform, user_id, group_id, account_id, scope) → str`
- **业务规则**：MD5 哈希；群聊 key = `platform[_account:xxx][_scope:xxx]_group_id`；私聊 key = `platform[_account:xxx][_scope:xxx]_user_id_private`
- **约束**：算法稳定但属于 src/ 内部实现；v4 插件需复制此算法

### 1.2.6 v4 SDK 基础设施（P-0~6 已完成）

- **MaiBotPlugin 基类**：`plugin_id`、`scopes`、`on_load()`、`on_unload()`、`on_config_update()`、`ctx` 属性
- **PluginContext**：`ctx.send`（SendContext，5 种消息类型）、`ctx.storage`（StorageContext，get/set/delete）、`ctx.logger`（LoggerContext）、`ctx.emit_event()`、`ctx.get_session_info()`
- **@Tool/@Event 装饰器**：声明式组件注册，PluginLoader 自动收集
- **RunnerEndpoint**：gRPC 双向流 + 一元 RPC 客户端，自动重连，ToolRouter 路由
- **HostServicer**：Connect 双向流 + RegisterComponents + SendMessage/StorageGet/Set/Delete/GetSessionInfo RPC
- **MCPHostBridge**：ToolProvider 注册/注销 + Event 分发
- **ScopeVocabulary**：54 个 scope 条目，11 个资源域

# 二、增量设计方案

## 2.1 实现模型

### 2.1.1 上下文视图

```
@startuml
skinparam componentStyle rectangle

package "NapCatQQ (外部进程)" as napcat {
    [WebSocket Server] as ws
    [HTTP API] as http
}

package "napcat-adapter (v4 Plugin Runner 进程)" as adapter {
    [NapCatTransportClient] as transport
    [NapCatEventRouter] as router
    [InboundCodec] as in_codec
    [OutboundCodec] as out_codec
    [NapCatAdapterPlugin] as plugin
    [SessionIdMapper] as sid_map
    [MessageDeduplicator] as dedup
    [EventBuffer] as buffer
}

package "MaiBot Host (主程序)" as host {
    [HostServicer] as servicer
    [MCPHostBridge] as bridge
    [EventDispatcher] as dispatcher
    [ChatBot] as chatbot
    [PlatformIOManager] as pio
}

ws --|> transport : WS 事件推送
transport --|> router : 原始 payload
router --|> in_codec : 解析
router --|> dedup : 去重检查
in_codec --|> plugin : Event payload
plugin --|> buffer : 缓存（gRPC 断连时）
plugin --|> servicer : gRPC Event 推送
servicer --|> bridge : Event 分发
bridge --|> dispatcher : napcat.* Event
dispatcher --|> chatbot : CoreMessage 注入

chatbot --|> pio : 出站消息
pio --|> servicer : InvokeTool
servicer --|> plugin : gRPC Tool 调用
plugin --|> out_codec : 构造 OneBot action
plugin --|> sid_map : session_id → QQ ID
out_codec --|> http : HTTP API 调用

@enduml
```

### 2.1.2 服务/组件总体架构

```
@startuml
skinparam componentStyle rectangle

package "napcat-adapter (plugins/maibot-team.napcat-adapter/)" {
    
    package "核心层" {
        [NapCatAdapterPlugin\n(MaiBotPlugin 子类)] as plugin
        note right of plugin
          plugin_id = "maibot-team.napcat-adapter"
          scopes = 9 个
          on_load/on_unload/on_config_update
        end note
    }
    
    package "传输层" {
        [NapCatTransportClient\n(aiohttp WS 客户端)] as transport
        note right of transport
          正向 WS 连接
          echo 请求-响应匹配
          自动重连
        end note
    }
    
    package "编解码层" {
        [InboundCodec\n(OneBot → Event payload)] as in_codec
        [OutboundCodec\n(Tool args → OneBot action)] as out_codec
        [NoticeCodec\n(OneBot notice → Event payload)] as notice_codec
    }
    
    package "路由层" {
        [NapCatEventRouter\n(post_type 分发)] as router
        [NapCatChatFilter\n(聊天名单过滤)] as chat_filter
        [NapCatOfficialBotGuard\n(官方机器人屏蔽)] as bot_guard
        [NapCatRegexFilter\n(正则过滤)] as regex_filter
    }
    
    package "辅助层" {
        [SessionIdMapper\n(session_id ↔ QQ ID)] as sid_map
        [MessageDeduplicator\n(message_id LRU 去重)] as dedup
        [EventBuffer\n(gRPC 断连缓存)] as buffer
        [NapCatHeartbeatMonitor\n(心跳监控)] as heartbeat
        [NapCatBanTracker\n(禁言追踪)] as ban_tracker
    }
    
    package "配置层" {
        [NapCatPluginSettings\n(配置模型)] as config
    }
}

plugin --> transport : 启动/停止
plugin --> router : 事件分发
router --> in_codec : 消息解析
router --> notice_codec : 通知解析
router --> chat_filter : 名单过滤
router --> bot_guard : 机器人屏蔽
router --> regex_filter : 正则过滤
router --> dedup : 去重
plugin --> out_codec : 出站构造
plugin --> sid_map : ID 映射
plugin --> buffer : 事件缓存
router --> heartbeat : 心跳
router --> ban_tracker : 禁言

@enduml
```

### 2.1.3 实现设计文档

#### 2.1.3.1 消息接收流（状态机）

```
@startuml
state "WS_DISCONNECTED" as discon
state "WS_CONNECTING" as connecting
state "WS_CONNECTED" as connected
state "WS_RECONNECTING" as recon

[*] --> discon : on_load
discon --> connecting : transport.start()
connecting --> connected : WS 握手成功
connecting --> recon : WS 握手失败
connected --> discon : transport.stop()\n(on_unload)
connected --> recon : WS 断开
recon --> connecting : 重连间隔到期
recon --> discon : 重连次数耗尽

state connected {
    [*] --> payload_received : WS 消息
    payload_received --> echo_check : echo 字段？
    echo_check --> resolve_action : 有 echo\n(动作响应)
    echo_check --> post_type_dispatch : 无 echo\n(事件推送)
    post_type_dispatch --> message_flow : post_type=message
    post_type_dispatch --> notice_flow : post_type=notice
    post_type_dispatch --> meta_flow : post_type=meta_event
    
    message_flow --> self_filter : 自身消息？
    self_filter --> chat_filter : 非自身消息
    chat_filter --> bot_guard : 名单内
    bot_guard --> dedup_check : 非官方机器人
    dedup_check --> in_codec : 未去重
    in_codec --> emit_event : ctx.emit_event()
    emit_flow : ctx.emit_event("napcat.message", payload)
    
    notice_flow --> chat_filter2 : 名单过滤
    chat_filter2 --> notice_codec : 名单内
    notice_codec --> emit_notice : ctx.emit_event("napcat.notice", payload)
}

@enduml
```

#### 2.1.3.2 消息发送流（活动图）

```
@startuml
start
:Host 下发 InvokeTool\n(napcat.send_text 等);
:ToolRouter 路由到\n对应 handler;
:从 args 提取 session_id;
:SessionIdMapper 反解\nsession_id → group_id/user_id;
if (反解成功？) then (是)
else (否)
    :返回 {"success": false,\n"error": "SESSION_NOT_FOUND"};
    stop
endif
:OutboundCodec 构造\nOneBot action + params;
:transport.call_action()\n调用 NapCatQQ HTTP API;
if (调用成功？) then (是)
    :提取 message_id;
    :SessionIdMapper 记录\nmessage_id 映射;
    :返回 {"success": true,\n"message_id": "xxx"};
else (否)
    :返回 {"success": false,\n"error": "API_ERROR"};
endif
stop
@enduml
```

#### 2.1.3.3 gRPC 断连事件缓存（流程）

```
@startuml
start
:NapCatQQ 推送事件;
:InboundCodec 解析;
:检查 RunnerEndpoint.is_ready;
if (gRPC 就绪？) then (是)
    :ctx.emit_event() 直接推送;
else (否)
    :EventBuffer.push(event);
    note right: 内存队列，上限 1000 条
    :等待 gRPC 重连;
endif
:gRPC 重连成功;
:EventBuffer.flush();
note right: 逐条 emit_event() 重放
:清空缓存;
stop
@enduml
```

## 2.2 接口设计

### 2.2.1 总体设计

napcat-adapter 声明 3 个 Event 和 5 个 Tool，覆盖 QQ 平台消息收发全链路。

| 组件类型 | 名称 | 稳定性 | 用途 |
|---------|------|--------|------|
| Event | napcat.message | 稳定 | 私聊消息推送 |
| Event | napcat.group_message | 稳定 | 群聊消息推送 |
| Event | napcat.notice | 稳定 | 通知事件推送 |
| Tool | napcat.send_text | 稳定 | 发送文本消息 |
| Tool | napcat.send_image | 稳定 | 发送图片消息 |
| Tool | napcat.send_emoji | 稳定 | 发送表情包 |
| Tool | napcat.send_forward | 稳定 | 发送转发消息 |
| Tool | napcat.send_hybrid | 稳定 | 发送图文混合消息 |

**Scope 声明**（9 个）：

| Scope | 用途 | 风险等级 |
|-------|------|---------|
| message:send:text | 发送文本消息 | low |
| message:send:image | 发送图片消息 | medium |
| message:send:emoji | 发送表情包 | medium |
| message:send:forward | 发送转发消息 | medium |
| message:send:hybrid | 发送图文混合消息 | medium |
| session:read:detail | 查询会话详情 | low |
| database:read:self | 读取自身键值存储（ID 映射） | low |
| database:write:self | 写入自身键值存储（ID 映射） | low |
| system:execute:command | 发送平台命令 | high |

### 2.2.2 接口清单

#### napcat.message（Event）

```python
@Event(
    name="napcat.message",
    description="QQ 私聊消息事件",
    event_schema={...},  # 见 2.3 数据模型
)
async def on_private_message(self) -> None:
    """声明用，运行时不调用。"""
```

**Event payload 字段**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| session_id | str | 是 | 主程序格式会话 ID |
| platform | str | 是 | 固定 "qq" |
| sender_id | str | 是 | 发送者 QQ 号 |
| sender_name | str | 是 | 发送者昵称 |
| plain_text | str | 是 | 消息纯文本 |
| message_segments | str | 是 | OneBot 11 消息段数组 JSON |
| message_id | str | 是 | NapCatQQ 消息 ID |
| is_notify | bool | 是 | 固定 False |
| additional_config | str | 是 | JSON，含 napcat_notice_type 等 |

#### napcat.group_message（Event）

与 napcat.message 结构相同，additional_config 中额外包含 group_id。

#### napcat.notice（Event）

```python
@Event(
    name="napcat.notice",
    description="QQ 通知事件（戳一戳、撤回、禁言等）",
    event_schema={...},
)
async def on_notice(self) -> None:
    """声明用，运行时不调用。"""
```

**Event payload 字段**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| session_id | str | 是 | 主程序格式会话 ID |
| platform | str | 是 | 固定 "qq" |
| is_notify | bool | 是 | 固定 True |
| napcat_notice_type | str | 是 | OneBot 11 notice_type |
| napcat_notice_sub_type | str | 否 | OneBot 11 sub_type |
| napcat_notice_payload | str | 是 | 完整通知事件 JSON |
| sender_id | str | 否 | 操作者 QQ 号 |
| group_id | str | 否 | 群号 |

#### napcat.send_text（Tool）

```python
@Tool(
    name="napcat.send_text",
    description="向 QQ 会话发送文本消息",
    parameters_schema={
        "type": "object",
        "properties": {
            "session_id": {"type": "string", "description": "目标会话 ID"},
            "text": {"type": "string", "description": "文本内容"},
            "reply_to": {"type": "string", "description": "回复目标消息 ID（可选）"},
            "at_user_id": {"type": "string", "description": "@目标用户 ID（可选）"},
        },
        "required": ["session_id", "text"],
    },
    output_schema={
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "message_id": {"type": "string"},
            "error": {"type": "string"},
        },
    },
)
async def send_text(self, args: dict[str, Any]) -> dict[str, Any]:
```

**业务说明**：Host 通过 InvokeTool 调用，插件将 session_id 反解为 QQ group_id/user_id，构造 OneBot 11 send_msg action，调用 NapCatQQ HTTP API。

**前置条件**：session_id 可反解为有效 QQ ID；NapCatQQ 连接可用。

**后置条件**：QQ 目标会话收到文本消息；返回 message_id 供后续引用。

**异常映射**：

| 场景 | 错误码 |
|------|--------|
| session_id 无法映射 | SESSION_NOT_FOUND |
| NapCatQQ API 调用失败 | API_ERROR |
| NapCatQQ 限频 | RATE_LIMITED |
| 消息内容为空 | EMPTY_MESSAGE |

#### napcat.send_image（Tool）

```python
@Tool(
    name="napcat.send_image",
    description="向 QQ 会话发送图片消息",
    parameters_schema={
        "type": "object",
        "properties": {
            "session_id": {"type": "string"},
            "image_base64": {"type": "string", "description": "图片 base64 数据"},
            "reply_to": {"type": "string"},
        },
        "required": ["session_id", "image_base64"],
    },
)
async def send_image(self, args: dict[str, Any]) -> dict[str, Any]:
```

#### napcat.send_emoji（Tool）

```python
@Tool(
    name="napcat.send_emoji",
    description="向 QQ 会话发送表情包",
    parameters_schema={
        "type": "object",
        "properties": {
            "session_id": {"type": "string"},
            "emoji_base64": {"type": "string", "description": "表情包 base64 数据"},
        },
        "required": ["session_id", "emoji_base64"],
    },
)
async def send_emoji(self, args: dict[str, Any]) -> dict[str, Any]:
```

#### napcat.send_forward（Tool）

```python
@Tool(
    name="napcat.send_forward",
    description="向 QQ 会话发送转发消息",
    parameters_schema={
        "type": "object",
        "properties": {
            "session_id": {"type": "string"},
            "forward_message_id": {"type": "string", "description": "转发消息 ID"},
        },
        "required": ["session_id", "forward_message_id"],
    },
)
async def send_forward(self, args: dict[str, Any]) -> dict[str, Any]:
```

#### napcat.send_hybrid（Tool）

```python
@Tool(
    name="napcat.send_hybrid",
    description="向 QQ 会话发送图文混合消息",
    parameters_schema={
        "type": "object",
        "properties": {
            "session_id": {"type": "string"},
            "hybrid_payload": {"type": "string", "description": "混合消息 JSON"},
            "reply_to": {"type": "string"},
            "at_user_id": {"type": "string"},
        },
        "required": ["session_id", "hybrid_payload"],
    },
)
async def send_hybrid(self, args: dict[str, Any]) -> dict[str, Any]:
```

## 2.3 数据模型

### 2.3.1 设计目标

1. 支持消息收发全链路：OneBot 11 事件 → Event payload → CoreMessage → Tool 调用 → OneBot 11 action
2. session_id 双向映射：入站时从 QQ ID 计算 session_id，出站时从 session_id 反解 QQ ID
3. 消息 ID 映射持久化：插件重启后可恢复
4. 事件缓存：gRPC 断连时不丢失入站事件

### 2.3.2 模型实现

#### SessionIdMapper（session_id 双向映射）

```
@startuml
class SessionIdMapper {
    - _forward_map: dict[str, str]\nsession_id → "group:{gid}" / "private:{uid}"
    - _reverse_map: dict[str, str]\n"group:{gid}" → session_id
    - _storage: StorageContext
    
    + calculate_session_id(platform, user_id, group_id, account_id, scope) str
    + register_session(session_id, group_id, user_id) void
    + resolve_qq_ids(session_id) tuple[str, str]\n→ (group_id, user_id)
    + persist() async void
    + restore() async void
}

note right of SessionIdMapper
  calculate_session_id 复制 SessionUtils 算法：
  群聊: MD5("qq[_account:xxx][_scope:xxx]_{group_id}")
  私聊: MD5("qq[_account:xxx][_scope:xxx]_{user_id}_private")
  
  register_session 在入站时调用，
  建立 session_id ↔ QQ ID 双向映射。
  
  persist/restore 使用 ctx.storage
  键前缀: "sid_map:"
  
  resolve_qq_ids 优先查内存映射，
  未命中则尝试从 session_id 的
  additional_config 中提取。
end note
@enduml
```

**核心映射逻辑**：

- **入站**：从 OneBot 11 事件提取 `group_id`/`user_id`，调用 `calculate_session_id("qq", user_id, group_id, account_id)` 生成 session_id，同时调用 `register_session()` 建立双向映射
- **出站**：Tool handler 收到 session_id，调用 `resolve_qq_ids(session_id)` 获取 `(group_id, user_id)`，构造 OneBot 11 action

#### MessageDeduplicator（消息去重）

```
@startuml
class MessageDeduplicator {
    - _seen: OrderedDict[str, float]\nmessage_id → timestamp
    - _max_size: int = 1000
    - _ttl_sec: float = 300.0
    
    + is_duplicate(message_id) bool
    + record(message_id) void
    + cleanup() void
}

note right of MessageDeduplicator
  LRU 缓存，最多保留 1000 条。
  TTL 5 分钟，过期自动清理。
  cleanup() 每次检查时惰性执行。
end note
@enduml
```

#### EventBuffer（gRPC 断连事件缓存）

```
@startuml
class EventBuffer {
    - _queue: asyncio.Queue\n上限由配置决定（默认 1000）
    - _dropped_count: int
    - _hard_limit: int = 5000
    
    + push(event_name, payload) bool\n队列满时丢弃最旧事件
    + flush(ctx) async int\n重放所有缓存事件，失败时保留未重放部分
    + clear() void
    + size() int
}

note right of EventBuffer
  push() 在 gRPC 断连时调用。
  flush() 在 gRPC 重连后调用，
  逐条 ctx.emit_event() 重放。
  如果 flush 期间 gRPC 再次断连，
  保留未重放的事件，不丢弃。
  返回成功重放的事件数。
  _hard_limit 为绝对上限（默认 5000），
  超过后强制丢弃最旧事件。
end note
@enduml
```

#### NapCatAdapterPlugin（插件主类）

```
@startuml
class NapCatAdapterPlugin {
    + plugin_id: str = "maibot-team.napcat-adapter"
    + plugin_version: str = "2.0.0"
    + scopes: list[str] = [9 个 scope]
    
    - _transport: NapCatTransportClient
    - _router: NapCatEventRouter
    - _in_codec: InboundCodec
    - _out_codec: OutboundCodec
    - _sid_mapper: SessionIdMapper
    - _dedup: MessageDeduplicator
    - _buffer: EventBuffer
    - _settings: NapCatPluginSettings
    
    + on_load() async void
    + on_unload() async void
    + on_config_update(config) async void
    
    + send_text(args) async dict
    + send_image(args) async dict
    + send_emoji(args) async dict
    + send_forward(args) async dict
    + send_hybrid(args) async dict
    
    - _handle_inbound(payload) async void
    - _handle_notice(payload) async void
    - _handle_meta(payload) async void
    - _emit_or_buffer(name, payload) async void
    - _restart_connection() async void
    - _stop_connection() async void
}

@enduml
```

## 2.4 配置设计

### 2.4.1 manifest.json（v3 格式）

```json
{
    "manifest_version": 3,
    "id": "maibot-team.napcat-adapter",
    "version": "2.0.0",
    "name": "NapCat 适配器",
    "description": "QQ 平台消息收发适配器，通过 NapCatQQ OneBot 11 协议通信",
    "author": {
        "name": "MaiBot Team",
        "url": "https://github.com/Mai-with-u"
    },
    "license": "GPL-3.0-or-later",
    "host_application": {
        "min_version": "1.0.0"
    },
    "sdk": {
        "min_version": "4.0.0"
    },
    "scopes": [
        "message:send:text",
        "message:send:image",
        "message:send:emoji",
        "message:send:forward",
        "message:send:hybrid",
        "session:read:detail",
        "database:read:self",
        "database:write:self",
        "system:execute:command"
    ]
}
```

### 2.4.2 config.toml（插件配置）

```toml
[napcat_server]
# NapCatQQ WebSocket Server 地址
ws_url = "ws://127.0.0.1:3001"
# NapCatQQ HTTP API 地址
http_url = "http://127.0.0.1:3000"
# NapCatQQ 鉴权 token（可选）
access_token = ""
# 连接标识（多实例时区分）
connection_id = ""

[reconnect]
# WebSocket 重连最大次数
max_retries = 10
# WebSocket 重连间隔秒数
interval_sec = 5

[buffer]
# gRPC 断连时的事件缓存上限
event_buffer_size = 1000

[chat]
# 启用聊天名单过滤
enable_chat_list_filter = false
# 群聊白名单（为空则不过滤）
group_list = []
# 私聊白名单（为空则不过滤）
private_list = []
# 屏蔽 QQ 官方机器人
ban_qq_bot = true
# 忽略自身消息
ignore_self_message = true

[filters]
# 启用正则消息过滤
regex_filter_enabled = false
# 过滤模式：whitelist（白名单）/ blacklist（黑名单）
regex_filter_mode = "whitelist"
# 正则过滤规则列表
regex_filter_patterns = []
```

### 2.4.3 配置变更响应

`on_config_update()` 收到配置更新后：
1. 解析新配置到 `NapCatPluginSettings`
2. 调用 `_stop_connection()` 断开当前连接
3. 调用 `_restart_connection()` 使用新配置重连
4. 重载正则过滤规则

## 2.5 过渡方案：与 maim_message 双链路并存

### 2.5.1 并存策略

napcat-adapter v4 与 maim_message 链路可同时运行，通过 PlatformIO 路由键区分：

| 链路 | RouteKey | DriverKind | 优先级 |
|------|----------|------------|--------|
| maim_message | platform=qq, account_id=legacy | LEGACY | 0（默认） |
| napcat-adapter v4 | platform=qq, account_id={self_id} | PLUGIN | 10（优先） |

**并存规则**：
1. napcat-adapter v4 注册时声明 `account_id`（从 NapCatQQ 获取的 self_id），与 maim_message 的 legacy 驱动不冲突
2. 出站消息优先路由到 v4 驱动（优先级更高），v4 不可用时回退到 maim_message
3. 入站消息：两条链路可能同时收到相同事件，由 PlatformIO 去重（基于 external_message_id）

### 2.5.2 切换流程

1. **初始状态**：maim_message 链路独占运行
2. **安装 v4 插件**：napcat-adapter v4 加载，注册为 platform=qq 的 PLUGIN 驱动
3. **双链路运行**：两条链路同时收发，v4 优先出站，入站由 PlatformIO 去重
4. **验证通过后**：禁用 maim_message 的 QQ 平台路由，v4 独占运行
5. **最终状态**：maim_message 仅保留 WebUI/API Server 功能，QQ 平台完全由 v4 接管

### 2.5.3 回退策略

若 v4 链路出现问题：
1. 停止 napcat-adapter v4 插件（Host 发送 ShutdownRequest）
2. PlatformIO 自动回退到 maim_message legacy 驱动
3. 无需修改任何配置，消息收发立即恢复

## 2.6 Host 侧集成点（P-5 范围，非插件代码）

以下变更属于主程序代码（src/），是 napcat-adapter v4 正常运行的前提条件，属于 Phoenix-5 集成范围：

### 2.6.1 EventDispatcher 增强

当前 EventDispatcher 仅记录日志。需增强为：

1. **napcat.message / napcat.group_message**：构造 `message_data` dict（与 maim_message 格式兼容），调用 `ChatBot.message_process(message_data)`
2. **napcat.notice**：构造通知消息 dict，设置 `is_notify=True`，调用 `ChatBot.receive_message()`

**关键映射**：Event payload 中的字段需映射为 `message_data` 格式：
- `session_id` → `message_info.session_id`
- `sender_id` → `message_info.user_info.user_id`
- `sender_name` → `message_info.user_info.user_nickname`
- `plain_text` → `processed_plain_text`
- `message_segments` → 需转换为 maim_message.Seg 格式
- `napcat_notice_sub_type` → `additional_config.napcat_notice_sub_type`

### 2.6.2 v4 PlatformIO 驱动

napcat-adapter 注册后，MCPHostBridge 需自动创建 v4 版 PluginPlatformDriver：
- `platform = "qq"`
- `account_id = self_id`（从 Event payload 中提取）
- `supports_send = True`
- 出站时调用插件的 `napcat.send_*` Tool（通过 InvokeTool RPC）

### 2.6.3 消息 ID echo 回填

napcat-adapter 通过 Event 推送 echo 信息时，Host 侧需调用 `MessageUtils.update_message_id_async()` 更新映射。

**v4 echo 回填完整路径**：

1. **出站**：Tool handler 调用 `transport.call_action("send_msg", params)` 时，NapCatQQ 返回 `{"message_id": "xxx"}`
2. **插件侧**：Tool handler 将 `message_id` 写入返回结果 `{"success": true, "message_id": "xxx"}`
3. **Host 侧**：InvokeTool 返回后，Host 从结果中提取 `message_id`，更新内部映射
4. **入站 echo**：NapCatQQ 通过 WS 回传自身发送的消息事件（`self_id == sender_user_id`），插件过滤自身消息时，将 `message_id` 与出站 echo 关联
5. **持久化**：插件通过 `ctx.storage` 存储 `echo:{internal_id} → {napcat_message_id}` 映射，重启后可恢复

## 2.7 目录结构

```
plugins/maibot-team.napcat-adapter/
├── __init__.py              # create_plugin() 入口
├── plugin.py                # NapCatAdapterPlugin 主类
├── manifest.json            # Manifest v3
├── config.toml              # 插件配置
├── config.py                # NapCatPluginSettings 配置模型
├── transport.py             # NapCatTransportClient WS 客户端
├── session_mapper.py        # SessionIdMapper 双向映射
├── dedup.py                 # MessageDeduplicator 去重
├── event_buffer.py          # EventBuffer gRPC 断连缓存
├── constants.py             # 常量定义
├── types.py                 # 类型定义
├── qq_emoji_list.py         # QQ 表情 ID 列表
├── codecs/
│   ├── inbound/
│   │   ├── message_codec.py # 入站消息编解码
│   │   ├── notice_codec.py  # 入站通知编解码
│   │   ├── text.py          # CQ 码/文本处理
│   │   └── cards.py         # 卡片消息处理
│   └── outbound/
│       └── message_codec.py # 出站消息编解码
├── filters.py               # 聊天名单/正则过滤
├── heartbeat_monitor.py     # 心跳监控
├── runtime_state.py         # 运行时状态
└── services/
    ├── __init__.py
    ├── query_service.py     # QQ 查询服务
    ├── official_bot_guard.py # 官方机器人屏蔽
    ├── ban_tracker.py       # 禁言追踪
    └── ban_state_store.py   # 禁言状态存储
```

**与 v1 的差异**：
- 新增 `session_mapper.py`、`dedup.py`、`event_buffer.py`（v4 独有需求）
- 删除 `runtime/router.py`、`runtime/builder.py`、`runtime/bundle.py`（v1 运行时架构，v4 简化）
- 删除 `apis/` 目录（v1 通过 @MessageGateway 暴露 API，v4 通过 @Tool 暴露）
- `plugin.py` 从继承 v1 MaiBotPlugin + Mixin 改为继承 v4 MaiBotPlugin + @Tool/@Event