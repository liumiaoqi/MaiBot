# Phoenix-7：napcat-adapter v4 插件重写 — 需求规格

# **1. 组件定位**

## **1.1 核心职责**

将 NapCatQQ（OneBot 11 协议实现）的消息收发能力封装为 MaiBot v4 插件，通过 gRPC 双向流与 Host 通信，替代当前内置于主程序的 maim_message 链路。

## **1.2 核心输入**

1. **NapCatQQ OneBot 11 WebSocket 事件流**：NapCatQQ 通过 WebSocket Server 推送的 OneBot 11 事件（消息事件、通知事件、元事件、请求事件）
2. **Host Tool 调用请求**：Host 通过 gRPC 下发的 Tool 调用请求（发送消息、获取消息等）
3. **插件生命周期信号**：Host 通过 gRPC 下发的 on_load/on_unload 信号
4. **NapCatQQ OneBot 11 HTTP API 响应**：调用 NapCatQQ HTTP API 后返回的响应

## **1.3 核心输出**

1. **v4 Event 推送**：通过 gRPC 双向流向 Host 推送 QQ 消息事件、通知事件
2. **Tool 执行结果**：通过 gRPC 返回发送消息等 Tool 的执行结果
3. **会话信息查询结果**：通过 SDK RPC 返回 QQ 会话的详细信息
4. **NapCatQQ OneBot 11 HTTP API 调用**：向 NapCatQQ 发送消息、获取消息等 API 请求

## **1.4 职责边界**

- **不修改**主程序代码（src/ 下任何文件），napcat-adapter 作为独立 v4 插件运行在 plugins/ 目录下
- **不实现**消息预处理逻辑（图片描述、语音转写、表情包识别等），这些由主程序 SessionMessage.process() 完成
- **不实现**通知分类逻辑（NoticeKind 映射），仅原样传递通知子类型，分类由主程序 NapCatNoticeClassifier 完成
- **不实现**会话管理逻辑（会话创建、会话名缓存等），仅查询和上报，管理由主程序 SessionLifecyclePort 完成
- **不替代** maim_message 库的现有功能（WebUI 聊天室、API Server 等），仅替代 QQ 平台的消息收发链路
- **不处理** WebUI 平台消息，WebUI 消息走独立链路

# **2. 领域术语**

**napcat-adapter**
: MaiBot 的 QQ 平台适配器插件，封装 NapCatQQ 的 OneBot 11 协议通信能力，以 v4 插件形式运行。

**NapCatQQ**
: QQNT 的 OneBot 11 协议实现（TypeScript 项目），通过 WebSocket/HTTP 提供 QQ 消息收发能力。
: 备注：NapCatQQ 是独立进程，napcat-adapter 通过网络协议与其通信。

**OneBot 11**
: QQ 机器人标准通信协议，定义了事件上报格式和 HTTP/WebSocket API。
: 备注：NapCatQQ 实现了 OneBot 11 协议，并扩展了部分 NapCat 专有字段。

**消息事件**
: OneBot 11 中 post_type=message 的事件，包含私聊消息和群聊消息。

**通知事件**
: OneBot 11 中 post_type=notice 的事件，包含戳一戳、撤回、禁言、入群退群等。
: 备注：NapCatQQ 使用 notice_type=notify + sub_type 区分子类型（如 poke、input_status）。

**元事件**
: OneBot 11 中 post_type=meta_event 的事件，包含心跳和生命周期事件。

**请求事件**
: OneBot 11 中 post_type=request 的事件，包含加好友请求和加群请求。

**CQ 码**
: OneBot 11 的文本消息格式，用于在纯文本中嵌入图片、@、表情等富媒体。
: 备注：NapCatQQ 同时支持 CQ 码和数组格式的消息段。

**消息段（Message Segment）**
: OneBot 11 的结构化消息格式，每条消息由多个 type+data 的消息段组成。

**napcat_notice_sub_type**
: NapCatQQ 通知事件中的子类型标识，如 poke、input_status、group_ban 等。
: 备注：主程序通过此字段映射到平台无关的 NoticeKind。

# **3. 角色与边界**

## **3.1 核心角色**

- **MaiBot 用户**：通过 QQ 与机器人交互的终端用户，发送消息、戳一戳、撤回消息等
- **MaiBot 管理员**：配置 napcat-adapter 的 WebSocket 连接参数、审批 scope 授权
- **插件开发者**：参考 napcat-adapter 的实现作为 v4 插件开发范例

## **3.2 外部系统**

- **NapCatQQ**：QQNT 的 OneBot 11 协议实现，提供 WebSocket 事件推送和 HTTP API
- **MaiBot Host**：v2 主程序，通过 gRPC 接收插件 Event 推送和下发 Tool 调用
- **maim_message**：当前主程序的消息传输库，napcat-adapter 重写后将逐步替代其 QQ 平台链路
- **Platform IO**：主程序的平台消息路由层，napcat-adapter 需注册为 PluginPlatformDriver

## **3.3 交互上下文**

```
                    ┌──────────────────────────────────────────────────┐
                    │                  napcat-adapter                  │
                    │              (v4 Plugin Runner 进程)              │
                    │                                                  │
  NapCatQQ          │  ┌──────────┐  gRPC 双向流  ┌──────────────┐   │  MaiBot Host
  WebSocket ────────┼──│ WS Client│──────────────▶│ HostEndpoint │───┼──▶ CoreMessage
  事件推送          │  └──────────┘  Event 推送   └──────────────┘   │   处理管道
                    │                                                  │
                    │  ┌──────────┐  gRPC 双向流  ┌──────────────┐   │
  NapCatQQ          │  │HTTP Client│◀──────────────│ HostEndpoint │───┼─── Tool 调用
  HTTP API ◀────────┼──│(发送消息) │  Tool 请求   └──────────────┘   │   (send_msg)
                    │  └──────────┘              ┌──────────────┐   │
                    │                            │ HostEndpoint │───┼──▶ SessionInfo
                    │  ┌──────────┐  SDK RPC     └──────────────┘   │   查询
                    │  │PluginCtx │──────────────▶                    │
                    │  └──────────┘                                    │
                    └──────────────────────────────────────────────────┘
```

# **4. DFX约束**

## **4.1 性能**

1. 消息接收延迟：从 NapCatQQ 推送事件到 Host 收到 Event，端到端延迟 ≤200ms
2. 消息发送延迟：从 Host 下发 Tool 调用到 NapCatQQ HTTP API 返回，端到端延迟 ≤500ms
3. WebSocket 重连时间：连接断开后自动重连，重连间隔 ≤5s，最多重试 10 次
4. 事件推送吞吐量：支持 ≥100 条/秒的消息事件推送

## **4.2 可靠性**

1. WebSocket 连接断开后必须自动重连，不丢失重连期间 NapCatQQ 缓存的事件
2. 消息发送失败时必须返回明确错误，不静默吞错误
3. gRPC 连接断开时，插件必须优雅降级：缓存入站事件，待重连后重放
4. 插件启动时必须验证 NapCatQQ 连接可用性，不可用时在 on_load 中报告错误

## **4.3 安全性**

1. 必须声明并使用最小 scope 集合，不得声明未使用的 scope
2. NapCatQQ WebSocket 连接必须支持 access_token 鉴权
3. 插件不得存储 QQ 用户敏感信息（密码、token 等），仅传递必要字段
4. HTTP API 调用必须支持 access_token 鉴权

## **4.4 可维护性**

1. 插件代码必须位于 plugins/ 目录下独立仓库，不与主程序耦合
2. 所有 OneBot 11 事件类型和 API 调用必须有明确注释和类型定义
3. 日志必须使用 ctx.logger，不直接使用 print 或自定义 logger
4. 配置项通过 manifest 或插件配置文件声明，不硬编码

## **4.5 兼容性**

1. 必须兼容 NapCatQQ 当前版本（OneBot 11 协议）
2. 插件重写后，主程序的消息收发行为必须与当前 maim_message 链路一致（功能对等）
3. 插件必须支持与 maim_message 链路并存（过渡期双链路运行）
4. 通知事件的 napcat_notice_sub_type 字段必须与当前 notice_type_mapping.py 的映射兼容

# **5. 核心能力**

## **5.1 QQ 消息接收桥接**

### **5.1.1 业务规则**

1. **WebSocket 连接管理**：插件必须通过 WebSocket 连接 NapCatQQ 的事件推送服务
   a. 验收条件：插件启动后自动连接配置的 NapCatQQ WebSocket 地址 → 连接成功并开始接收事件

2. **私聊消息接收**：接收到 post_type=message + message_type=private 的 OneBot 11 事件后，转换为 v4 Event 推送给 Host
   a. 验收条件：QQ 用户发送私聊消息 → Host 收到包含 session_id、plain_text、sender_id 等字段的 Event

3. **群聊消息接收**：接收到 post_type=message + message_type=group 的 OneBot 11 事件后，转换为 v4 Event 推送给 Host
   a. 验收条件：QQ 群成员发送消息 → Host 收到包含 group_id、sender_id、plain_text 等字段的 Event

4. **消息段解析**：必须正确解析 OneBot 11 消息段数组（text、image、at、reply、face、mface、record、file 等），转换为主程序可识别的格式
   a. 验收条件：QQ 用户发送包含图片+文本的混合消息 → Event 中包含完整的消息段信息

5. **CQ 码兼容**：当 NapCatQQ 推送 CQ 码格式消息时，必须正确解析
   a. 验收条件：收到 CQ 码格式的消息 → 解析结果与数组格式一致

6. **消息去重**：必须对重复的 OneBot 11 事件进行去重（基于 message_id 或 time+user_id 组合）
   a. 验收条件：NapCatQQ 重推同一消息 → Host 仅收到一次 Event

7. **自身消息过滤**：必须过滤掉机器人自身发送的消息，不推送给 Host
   a. 验收条件：机器人发送消息后 NapCatQQ 回传自身消息事件 → Host 不收到该 Event

### **5.1.2 交互流程**

```
NapCatQQ          napcat-adapter              gRPC              Host
──────────────────────────────────────────────────────────────────────
WS 推送事件 ──▶ WS Client 接收
                解析 OneBot 11 JSON
                转换为 v4 Event 载荷
                过滤自身消息 ──────────────▶ Event 推送 ──▶ Host 接收
                去重检查                                    分发到 CoreMessage
```

### **5.1.3 异常场景**

1. **WebSocket 连接断开**
   a. 触发条件：NapCatQQ 进程重启或网络中断
   b. 系统行为：自动重连（指数退避，最多 10 次），重连期间缓存事件
   c. 用户感知：QQ 消息暂时无法送达机器人，重连后自动恢复

2. **OneBot 11 事件格式异常**
   a. 触发条件：收到无法解析的 OneBot 11 事件（缺少必填字段、格式错误）
   b. 系统行为：记录警告日志，跳过该事件，不中断主流程
   c. 用户感知：该消息被丢弃，其他消息正常处理

3. **gRPC 连接断开**
   a. 触发条件：Host 进程重启或 gRPC 通道异常
   b. 系统行为：缓存入站事件（内存队列，上限 1000 条），待 gRPC 重连后重放
   c. 用户感知：消息延迟送达，不丢失

4. **NapCatQQ access_token 鉴权失败**
   a. 触发条件：配置的 token 与 NapCatQQ 不匹配
   b. 系统行为：WebSocket 连接被拒绝，记录错误日志，按重连策略重试
   c. 用户感知：插件无法接收消息，日志显示鉴权失败

## **5.2 QQ 消息发送桥接**

### **5.2.1 业务规则**

1. **发送文本消息**：Host 通过 Tool 调用请求发送文本消息时，插件必须调用 NapCatQQ 的 send_msg API
   a. 验收条件：Host 下发 send_text Tool 调用 → QQ 目标会话收到文本消息

2. **发送图片消息**：Host 通过 Tool 调用请求发送图片时，插件必须调用 NapCatQQ 的 send_msg API 并传递图片数据
   a. 验收条件：Host 下发 send_image Tool 调用 → QQ 目标会话收到图片消息

3. **发送表情包消息**：Host 通过 Tool 调用请求发送表情包时，插件必须调用 NapCatQQ 的 send_msg API 并传递表情包数据
   a. 验收条件：Host 下发 send_emoji Tool 调用 → QQ 目标会话收到表情包

4. **发送混合消息**：Host 通过 Tool 调用请求发送图文混合消息时，插件必须调用 NapCatQQ 的 send_msg API 并构造消息段数组
   a. 验收条件：Host 下发 send_hybrid Tool 调用 → QQ 目标会话收到图文混合消息

5. **发送回复消息**：当 Tool 调用包含 reply_to 字段时，必须在消息段中包含 reply 消息段
   a. 验收条件：Host 下发包含 reply_to 的 Tool 调用 → QQ 目标会话收到回复消息

6. **发送 @ 消息**：当 Tool 调用包含 at_user 字段时，必须在消息段中包含 at 消息段
   a. 验收条件：Host 下发包含 at_user 的 Tool 调用 → QQ 目标会话收到 @消息

7. **消息 ID 回填**：NapCatQQ 返回的 message_id 必须回填给 Host，用于后续的回复引用和消息追踪
   a. 验收条件：发送消息后 NapCatQQ 返回 message_id → Tool 执行结果包含该 message_id

8. **session_id 到 QQ ID 映射**：必须将主程序的 session_id 映射为 NapCatQQ 的 group_id 或 user_id
   a. 验收条件：Host 传入 session_id → 插件正确解析为对应的 group_id 或 user_id

### **5.2.2 交互流程**

```
Host              gRPC              napcat-adapter              NapCatQQ
──────────────────────────────────────────────────────────────────────
Tool 调用 ──▶ Host 下发 ──▶ Runner 接收
                              解析 Tool 参数
                              session_id → group_id/user_id
                              构造 OneBot 11 消息段
                              调用 HTTP API ──────────────▶ send_msg
                              等待响应 ◀────────────────── 返回 message_id
                              返回 Tool 结果 ◀─── Host 接收
```

### **5.2.3 异常场景**

1. **NapCatQQ HTTP API 调用失败**
   a. 触发条件：NapCatQQ 进程不可用或 API 返回错误
   b. 系统行为：Tool 返回错误结果（包含错误描述），不重试
   c. 用户感知：消息发送失败，日志显示 API 错误

2. **session_id 无法映射**
   a. 触发条件：Host 传入的 session_id 无法解析为有效的 QQ group_id 或 user_id
   b. 系统行为：Tool 返回错误结果（SESSION_NOT_FOUND）
   c. 用户感知：消息发送失败，日志显示 session_id 无效

3. **消息段构造失败**
   a. 触发条件：图片 base64 解码失败或消息段格式不支持
   b. 系统行为：Tool 返回错误结果（INVALID_MESSAGE），记录错误日志
   c. 用户感知：消息发送失败

4. **NapCatQQ 发送频率限制**
   a. 触发条件：短时间内发送过多消息，触发 NapCatQQ 限频
   b. 系统行为：Tool 返回错误结果（RATE_LIMITED），记录警告日志
   c. 用户感知：消息发送延迟或失败

## **5.3 QQ 通知事件推送**

### **5.3.1 业务规则**

1. **戳一戳事件**：接收到 notice_type=notify + sub_type=poke 的通知后，转换为 v4 Event 推送给 Host
   a. 验收条件：QQ 用户戳机器人 → Host 收到 napcat_notice_sub_type=poke 的 Event

2. **输入状态事件**：接收到 notice_type=notify + sub_type=input_status 的通知后，转换为 v4 Event 推送给 Host
   a. 验收条件：QQ 用户正在输入 → Host 收到 napcat_notice_sub_type=input_status 的 Event

3. **群消息撤回事件**：接收到 notice_type=group_recall 的通知后，转换为 v4 Event 推送给 Host
   a. 验收条件：QQ 群消息被撤回 → Host 收到包含 message_id 的撤回 Event

4. **好友消息撤回事件**：接收到 notice_type=friend_recall 的通知后，转换为 v4 Event 推送给 Host
   a. 验收条件：QQ 私聊消息被撤回 → Host 收到包含 message_id 的撤回 Event

5. **群成员增减事件**：接收到 notice_type=group_increase/group_decrease 的通知后，转换为 v4 Event 推送给 Host
   a. 验收条件：QQ 群成员加入/退出 → Host 收到对应的 Event

6. **群管理变动事件**：接收到 notice_type=group_admin 的通知后，转换为 v4 Event 推送给 Host
   a. 验收条件：QQ 群管理员变动 → Host 收到对应的 Event

7. **群禁言事件**：接收到 notice_type=group_ban 的通知后，转换为 v4 Event 推送给 Host
   a. 验收条件：QQ 群成员被禁言/解禁 → Host 收到对应的 Event

8. **好友添加事件**：接收到 notice_type=friend_add 的通知后，转换为 v4 Event 推送给 Host
   a. 验收条件：QQ 好友添加成功 → Host 收到对应的 Event

9. **通知子类型透传**：所有通知事件必须透传 napcat_notice_sub_type 字段，不做分类判断
   a. 验收条件：任何 NapCatQQ 通知事件 → Event 中包含原始 napcat_notice_sub_type

10. **未知通知类型兼容**：收到未识别的通知类型时，不丢弃，仍推送 Event（napcat_notice_sub_type=unknown）
    a. 验收条件：收到 NapCatQQ 新增的通知类型 → Host 收到 napcat_notice_sub_type=unknown 的 Event

### **5.3.2 交互流程**

```
NapCatQQ          napcat-adapter              gRPC              Host
──────────────────────────────────────────────────────────────────────
WS 推送通知 ──▶ WS Client 接收
                解析 notice_type + sub_type
                构造 Event 载荷
                透传 napcat_notice_sub_type ──▶ Event 推送 ──▶ Host 接收
                                                           NapCatNoticeClassifier
                                                           映射为 NoticeKind
```

### **5.3.3 异常场景**

1. **通知事件缺少关键字段**
   a. 触发条件：通知事件缺少 group_id 或 user_id 等必要字段
   b. 系统行为：记录警告日志，仍推送 Event（缺失字段置为空字符串）
   c. 用户感知：通知信息不完整，但不中断处理

2. **通知事件格式变更**
   a. 触发条件：NapCatQQ 版本升级导致通知事件格式变化
   b. 系统行为：尽力解析，无法解析的字段放入 additional_config
   c. 用户感知：部分通知信息可能缺失，但核心功能不受影响

## **5.4 会话信息查询**

### **5.4.1 业务规则**

1. **群会话信息查询**：通过 SDK RPC 的 get_session_info 查询 QQ 群会话信息
   a. 验收条件：传入 QQ 群的 session_id → 返回 session_name、platform=qq、is_group_session=True

2. **私聊会话信息查询**：通过 SDK RPC 的 get_session_info 查询 QQ 私聊会话信息
   a. 验收条件：传入 QQ 私聊的 session_id → 返回 session_name、platform=qq、is_group_session=False

3. **会话列表查询**：通过 SDK RPC 查询所有 QQ 平台的会话列表
   a. 验收条件：调用查询 → 返回所有 platform=qq 的会话信息

### **5.4.2 异常场景**

1. **session_id 不存在**
   a. 触发条件：查询不存在的 session_id
   b. 系统行为：SDK RPC 返回 SESSION_NOT_FOUND
   c. 用户感知：查询结果为空

## **5.5 插件生命周期与配置**

### **5.5.1 业务规则**

1. **Manifest 声明**：必须使用 Manifest v3 格式声明插件元数据
   a. 验收条件：manifest.json 包含 manifest_version=3、id=maibot-team.napcat-adapter、scopes 列表

2. **Scope 声明**：必须声明所需的最小 scope 集合
   a. 验收条件：manifest.json 的 scopes 包含 message:send:text、message:send:image、message:send:emoji、message:send:hybrid、message:send:forward、session:read:detail、database:read:self、database:write:self、system:execute:command

3. **Tool 声明**：必须通过 @Tool 装饰器声明消息发送工具
   a. 验收条件：插件注册后 Host 的 ToolRegistry 中包含 napcat-adapter 声明的发送工具

4. **Event 声明**：必须通过 @Event 装饰器声明消息接收和通知事件
   a. 验收条件：插件注册后 Host 的 EventDispatcher 中包含 napcat-adapter 声明的事件

5. **配置管理**：NapCatQQ 的连接参数（WebSocket 地址、HTTP API 地址、access_token）必须通过插件配置管理
   a. 验收条件：修改配置后插件自动重连 NapCatQQ

6. **on_load 初始化**：插件加载时必须初始化 WebSocket 连接和 HTTP API 客户端
   a. 验收条件：Host 启动插件 → napcat-adapter 自动连接 NapCatQQ 并开始收发消息

7. **on_unload 清理**：插件卸载时必须关闭 WebSocket 连接和 HTTP API 客户端
   a. 验收条件：Host 停止插件 → napcat-adapter 断开所有连接并释放资源

8. **Platform IO 注册**：插件加载后必须向 Host 注册为 QQ 平台的 PluginPlatformDriver
   a. 验收条件：napcat-adapter 加载后，主程序的 Platform IO 路由表中存在 platform=qq 的 Plugin 驱动

### **5.5.2 异常场景**

1. **NapCatQQ 连接不可用**
   a. 触发条件：on_load 时 NapCatQQ 未启动或地址不可达
   b. 系统行为：on_load 成功（不阻塞其他插件），后台持续重连
   c. 用户感知：插件显示为已加载但未连接，日志显示连接失败

2. **配置缺失或无效**
   a. 触发条件：缺少 NapCatQQ WebSocket 地址等必要配置
   b. 系统行为：on_load 报错但不崩溃，等待配置更新
   c. 用户感知：插件无法正常工作，日志提示配置缺失

3. **Scope 未审批**
   a. 触发条件：用户未在 WebUI 审批 napcat-adapter 声明的 scope
   b. 系统行为：插件可加载但调用受限 API 时抛出 ScopeDeniedError
   c. 用户感知：消息发送等功能不可用，WebUI 提示需要审批 scope

## **5.6 消息 ID 映射与回填**

### **5.6.1 业务规则**

1. **出站消息 ID 映射**：发送消息时，必须将主程序的内部 message_id 与 NapCatQQ 返回的 message_id 建立映射
   a. 验收条件：发送消息后，主程序能通过内部 message_id 查到 NapCatQQ 的 message_id

2. **入站消息 ID 透传**：接收消息时，必须将 NapCatQQ 的 message_id 透传给主程序
   a. 验收条件：QQ 消息到达后，主程序的 CoreMessage 中包含 NapCatQQ 的 message_id

3. **消息 ID 回显**：NapCatQQ 通过 echo 机制回传实际 message_id 时，必须更新映射关系
   a. 验收条件：NapCatQQ 回传 echo 消息 → 主程序更新 message_id 映射

### **5.6.2 异常场景**

1. **消息 ID 映射丢失**
   a. 触发条件：插件重启导致内存中的映射丢失
   b. 系统行为：通过 database:read:self 持久化映射，重启后从存储恢复
   c. 用户感知：回复引用可能暂时失效，恢复后正常

# **6. 数据约束**

## **6.1 OneBot 11 消息事件**

1. **post_type**：必须为 "message"
2. **message_type**：必须为 "private" 或 "group"
3. **sub_type**：可选，如 "friend"、"group"、"normal" 等
4. **message_id**：NapCatQQ 分配的消息 ID（整数或字符串）
5. **user_id**：发送者 QQ 号（字符串）
6. **group_id**：群号（仅群聊，字符串）
7. **message**：消息内容，数组格式（消息段列表）或 CQ 码字符串
8. **raw_message**：原始消息内容（CQ 码格式）
9. **sender**：发送者信息对象，包含 user_id、nickname、card（群名片）等
10. **time**：消息时间戳（整数）
11. **self_id**：机器人自身 QQ 号（字符串）

## **6.2 OneBot 11 通知事件**

1. **post_type**：必须为 "notice"
2. **notice_type**：通知类型，如 "notify"、"group_recall"、"friend_recall"、"group_increase"、"group_decrease"、"group_admin"、"group_ban"、"friend_add" 等
3. **sub_type**：子类型（notify 类通知必须），如 "poke"、"input_status" 等
4. **group_id**：群号（群相关通知）
5. **user_id**：操作者 QQ 号
6. **operator_id**：执行操作的 QQ 号（撤回等）
7. **message_id**：被操作的消息 ID（撤回等）
8. **duration**：持续时间（禁言等）
9. **time**：通知时间戳

## **6.3 插件 Event 载荷（消息事件）**

1. **event_name**：napcat.message（私聊）或 napcat.group_message（群聊）
2. **session_id**：主程序格式的会话 ID
3. **platform**：必须为 "qq"
4. **sender_id**：发送者 QQ 号（字符串）
5. **sender_name**：发送者昵称或群名片
6. **plain_text**：消息纯文本内容
7. **message_segments**：OneBot 11 消息段数组（JSON 格式）
8. **message_id**：NapCatQQ 消息 ID
9. **is_notify**：必须为 False（消息事件）
10. **additional_config**：额外配置，包含 napcat_notice_type、napcat_notice_sub_type 等字段

## **6.4 插件 Event 载荷（通知事件）**

1. **event_name**：napcat.notice
2. **session_id**：主程序格式的会话 ID（群通知为群会话 ID，私聊通知为私聊会话 ID）
3. **platform**：必须为 "qq"
4. **is_notify**：必须为 True
5. **napcat_notice_type**：OneBot 11 的 notice_type 值
6. **napcat_notice_sub_type**：OneBot 11 的 sub_type 值（如有）
7. **napcat_notice_payload**：完整的通知事件 JSON（供主程序解析细节）
8. **sender_id**：操作者 QQ 号
9. **group_id**：群号（群相关通知）

## **6.5 插件 Tool 参数（发送消息）**

1. **session_id**：目标会话 ID（必填）
2. **message_type**：消息类型，TEXT/IMAGE/EMOJI/FORWARD/HYBRID（必填）
3. **text_content**：文本内容（message_type=TEXT 时必填）
4. **image_base64**：图片 base64 数据（message_type=IMAGE 时必填）
5. **emoji_base64**：表情包 base64 数据（message_type=EMOJI 时必填）
6. **forward_message_id**：转发消息 ID（message_type=FORWARD 时必填）
7. **hybrid_payload**：混合消息 JSON（message_type=HYBRID 时必填）
8. **reply_to**：回复目标消息 ID（可选）
9. **at_user_id**：@目标用户 ID（可选）

## **6.6 插件配置**

1. **napcat_ws_url**：NapCatQQ WebSocket Server 地址（如 ws://127.0.0.1:3001）
2. **napcat_http_url**：NapCatQQ HTTP API 地址（如 http://127.0.0.1:3000）
3. **napcat_access_token**：NapCatQQ 鉴权 token（可选）
4. **reconnect_max_retries**：WebSocket 重连最大次数（默认 10）
5. **reconnect_interval_sec**：WebSocket 重连间隔秒数（默认 5）
6. **event_buffer_size**：gRPC 断连时的事件缓存上限（默认 1000）