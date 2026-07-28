# Phoenix-6：SDK RPC 通道 — 需求规格

# **1. 组件定位**

## **1.1 核心职责**

实现 SDK v4 的 SendContext、StorageContext、PluginContext.get_session_info 的 gRPC 通道，使插件能通过 RPC 调用主程序能力（发消息、存取数据、查询会话信息），将 9 个占位方法变为真实可用的 API。

## **1.2 核心输入**

1. **Phoenix-1 gRPC 传输层**：Host/Runner 双向流 + 一元 RPC 框架
2. **Phoenix-2 MCP 组件模型**：SDK context.py 中的 9 个占位方法（SendContext 5 个 + StorageContext 3 个 + PluginContext.get_session_info 1 个）
3. **Phoenix-5 v2 主程序集成**：HostEndpoint 已接入 main.py 生命周期
4. **核心 Protocol 接口**：MessagePortV2（发消息）、SessionRepository（会话查询）
5. **现有 .proto 定义**：common.proto、plugin_host.proto、plugin_runner.proto

## **1.3 核心输出**

1. **新增 .proto RPC 定义**：SendMessage、Storage 操作、GetSessionInfo 的消息类型和 RPC 方法
2. **Host 端 RPC 实现**：转发到 MessagePortV2、存储服务、SessionRepository
3. **Runner 端 RPC 客户端**：RunnerEndpoint 新增客户端调用方法
4. **SDK 占位方法实现**：9 个占位方法调用真实 RPC 通道

## **1.4 职责边界**

- **不修改**现有 Connect 双向流和 RegisterComponents RPC
- **不实现**存储持久化后端（使用 JSON 文件简单实现，完整存储留给后续）
- **不修改** .proto 中已有的消息定义（只新增）
- **不修改** SDK 装饰器和 Manifest 格式

# **2. 领域术语**

**SDK RPC 通道**
: 插件通过 gRPC 调用主程序能力的通信管道。插件侧通过 SendContext/StorageContext/PluginContext 调用，底层通过 RunnerEndpoint → gRPC → HostServicer → 主程序 Protocol 接口完成。

**SendContext**
: 插件发送消息的上下文接口，提供 text/image/emoji/forward/hybrid 5 种发送方式。

**StorageContext**
: 插件存取键值数据的上下文接口，提供 get/set/delete 3 种操作。

**PluginContext.get_session_info**
: 插件查询会话信息的接口，返回 SessionInfo 快照。

# **3. 角色与边界**

## **3.1 核心角色**

- **插件开发者**：通过 SDK context API 发送消息、存取数据、查询会话
- **MaiBot 维护者**：需要 SDK API 真实可用，以便开发有实际功能的 v4 插件

## **3.2 外部系统**

- **MessagePortV2**：核心消息发送 Protocol，SendContext 的最终消费者
- **SessionRepository**：会话查询 Protocol，get_session_info 的最终消费者
- **HostEndpoint**：gRPC 服务端，接收 Runner 的 RPC 请求并转发到 Protocol
- **RunnerEndpoint**：gRPC 客户端，SDK context 调用的桥梁

## **3.3 交互上下文**

```
插件代码                    SDK                     gRPC                    主程序
─────────────────────────────────────────────────────────────────────────────────
ctx.send.text(sid, "hi") → SendContext.text() → SendMessage RPC → HostServicer
                                                                     ↓
                                                              MessagePortV2.send_message()

ctx.storage.get("k")     → StorageContext.get() → StorageGet RPC → HostServicer
                                                                   ↓
                                                            PerPluginStorage.get()

ctx.get_session_info(sid) → PluginContext → GetSessionInfo RPC → HostServicer
                                                                   ↓
                                                            SessionRepository.get_session()
```

# **4. DFX约束**

## **4.1 性能**

1. SendMessage RPC 延迟 ≤100ms（本地 gRPC 调用 + Protocol 转发）
2. StorageGet RPC 延迟 ≤10ms（本地 JSON 文件读取）
3. GetSessionInfo RPC 延迟 ≤50ms

## **4.2 可靠性**

1. RPC 调用失败时 SDK 抛出明确异常，不静默吞错误
2. Storage 数据持久化到 JSON 文件（per-plugin 隔离）
3. SendMessage 失败时返回错误信息，不重试（避免重复发送）

## **4.3 安全性**

1. 所有 RPC 调用前校验 scope（SendContext 需要 `message:send` scope，StorageContext 需要 `storage:read/write` scope，GetSessionInfo 需要 `session:read` scope）
2. Storage per-plugin 隔离——插件 A 无法访问插件 B 的数据
3. SendMessage 只能发到已授权的 session（scope 校验）

## **4.4 可维护性**

1. 新增 RPC 定义遵循现有 .proto 命名规范
2. Host 端 RPC 实现通过 Protocol 接口与具体组件解耦
3. SDK 占位方法改为调用 RunnerEndpoint 方法，不直接操作 gRPC channel

# **5. 核心能力**

## **5.1 SendContext RPC 通道**

### **5.1.1 业务规则**

1. **text(session_id, text)** → SendMessage RPC（type=TEXT）
   a. 验收条件：插件调用 `ctx.send.text(sid, "hello")` 后，目标会话收到文本消息

2. **image(session_id, image_base64)** → SendMessage RPC（type=IMAGE）
   a. 验收条件：插件调用 `ctx.send.image(sid, base64_str)` 后，目标会话收到图片消息

3. **emoji(session_id, emoji_base64)** → SendMessage RPC（type=EMOJI）
   a. 验收条件：插件调用 `ctx.send.emoji(sid, base64_str)` 后，目标会话收到表情消息

4. **forward(session_id, message_id)** → SendMessage RPC（type=FORWARD）
   a. 验收条件：插件调用 `ctx.send.forward(sid, mid)` 后，目标会话收到转发消息

5. **hybrid(session_id, segments)** → SendMessage RPC（type=HYBRID）
   a. 验收条件：插件调用 `ctx.send.hybrid(sid, segments)` 后，目标会话收到混合消息

### **5.1.2 异常场景**

1. **scope 不足**
   a. 触发条件：插件未声明 `message:send` scope
   b. 系统行为：SDK 抛出 ScopeDeniedError
   c. 用户感知：插件开发者看到明确错误

2. **session_id 不存在**
   a. 触发条件：发送到不存在的会话
   b. 系统行为：RPC 返回 SESSION_NOT_FOUND 错误
   c. 用户感知：插件收到错误响应

3. **MessagePortV2 发送失败**
   a. 触发条件：消息端口内部错误
   b. 系统行为：RPC 返回 SEND_FAILED 错误
   c. 用户感知：插件收到错误响应

## **5.2 StorageContext RPC 通道**

### **5.2.1 业务规则**

1. **get(key, default=None)** → StorageGet RPC
   a. 验收条件：`ctx.storage.set("k", "v")` 后 `ctx.storage.get("k")` 返回 `"v"`

2. **set(key, value)** → StorageSet RPC
   a. 验收条件：set 后 get 返回最新值

3. **delete(key)** → StorageDelete RPC
   a. 验收条件：delete 后 get 返回 default

### **5.2.2 异常场景**

1. **scope 不足**
   a. 触发条件：插件未声明 `storage:read` 或 `storage:write` scope
   b. 系统行为：SDK 抛出 ScopeDeniedError

2. **存储读写失败**
   a. 触发条件：JSON 文件损坏或磁盘满
   b. 系统行为：RPC 返回 STORAGE_ERROR
   c. 用户感知：插件收到错误响应

## **5.3 GetSessionInfo RPC 通道**

### **5.3.1 业务规则**

1. **get_session_info(session_id)** → GetSessionInfo RPC
   a. 验收条件：返回 SessionInfo 快照（session_id, session_name, platform 等）

### **5.3.2 异常场景**

1. **scope 不足**
   a. 触发条件：插件未声明 `session:read` scope
   b. 系统行为：SDK 抛出 ScopeDeniedError

2. **session_id 不存在**
   a. 触发条件：查询不存在的会话
   b. 系统行为：RPC 返回 SESSION_NOT_FOUND

# **6. 数据约束**

## **6.1 新增 .proto 消息**

### SendMessage RPC

```protobuf
message SendMessageRequest {
  string plugin_id = 1;
  string session_id = 2;
  string message_type = 3;  // TEXT/IMAGE/EMOJI/FORWARD/HYBRID
  string text_content = 4;  // TEXT 类型
  string image_base64 = 5;  // IMAGE/EMOJI 类型
  string forward_message_id = 6;  // FORWARD 类型
  string hybrid_payload = 7;  // HYBRID 类型（JSON）
}

message SendMessageResponse {
  bool success = 1;
  string error = 2;  // SESSION_NOT_FOUND / SEND_FAILED / SCOPE_DENIED
  string message_id = 3;  // 成功时返回消息 ID
}
```

### Storage RPC

```protobuf
message StorageGetRequest {
  string plugin_id = 1;
  string key = 2;
  string default_value = 3;  // JSON 编码的默认值
}

message StorageGetResponse {
  bool found = 1;
  string value = 2;  // JSON 编码的值
  string error = 3;
}

message StorageSetRequest {
  string plugin_id = 1;
  string key = 2;
  string value = 3;  // JSON 编码的值
}

message StorageSetResponse {
  bool success = 1;
  string error = 2;
}

message StorageDeleteRequest {
  string plugin_id = 1;
  string key = 2;
}

message StorageDeleteResponse {
  bool deleted = 1;
  string error = 2;
}
```

### GetSessionInfo RPC

```protobuf
message GetSessionInfoRequest {
  string plugin_id = 1;
  string session_id = 2;
}

message GetSessionInfoResponse {
  bool found = 1;
  string session_id = 2;
  string session_name = 3;
  string platform = 4;
  bool is_group_session = 5;
  string primary_agent_id = 6;
  string error = 7;
}
```

## **6.2 新增 .proto service 方法**

在 `plugin_host.proto` 的 `PluginHost` service 中新增：

```protobuf
rpc SendMessage(SendMessageRequest) returns (SendMessageResponse);
rpc StorageGet(StorageGetRequest) returns (StorageGetResponse);
rpc StorageSet(StorageSetRequest) returns (StorageSetResponse);
rpc StorageDelete(StorageDeleteRequest) returns (StorageDeleteResponse);
rpc GetSessionInfo(GetSessionInfoRequest) returns (GetSessionInfoResponse);
```

## **6.3 新增文件**

| 文件 | 职责 |
|------|------|
| `src/plugin_runtime_v2/host/storage_service.py` | Per-plugin JSON 文件存储服务 |
| `src/plugin_runtime_v2/runner/rpc_clients.py` | Runner 端 RPC 客户端封装（SendMessage/Storage/SessionInfo） |

## **6.4 修改文件**

| 文件 | 改动 |
|------|------|
| `src/plugin_runtime_v2/proto/plugin_host.proto` | +5 个 RPC 方法 + 消息定义 |
| `src/plugin_runtime_v2/host/servicer.py` | +5 个 RPC 实现 |
| `src/plugin_runtime_v2/host/endpoint.py` | +storage_service 注入 |
| `src/plugin_runtime_v2/runner/endpoint.py` | +RPC 客户端方法 |
| `src/plugin_runtime_v2/sdk/context.py` | 9 个占位方法改为调用 RPC |