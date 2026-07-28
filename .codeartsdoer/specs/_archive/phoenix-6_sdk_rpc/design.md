# Phoenix-6：SDK RPC 通道 — 技术设计

# **1. 设计目标**

实现 SDK v4 的 SendContext、StorageContext、PluginContext.get_session_info 的 gRPC 通道，将 9 个占位方法变为真实可用的 API。Runner 端通过 gRPC 一元 RPC 调用 Host 端，Host 端转发到核心 Protocol 接口。

# **2. 整体架构**

## **2.1 调用链**

```
插件代码                    SDK context              RunnerEndpoint           gRPC                HostServicer           Protocol
─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
ctx.send.text(sid, "hi") → SendContext.text()  → _runner.send_message() → SendMessage RPC → _servicer.SendMessage()
                                                                                                   ↓
                                                                                            MessagePortV2.send_message()

ctx.storage.get("k")     → StorageContext.get() → _runner.storage_get()  → StorageGet RPC  → _servicer.StorageGet()
                                                                                                   ↓
                                                                                            PerPluginStorage.get()

ctx.get_session_info(sid) → PluginContext       → _runner.get_session_info() → GetSessionInfo RPC → _servicer.GetSessionInfo()
                                                                                                   ↓
                                                                                            SessionRepository.get_session()
```

## **2.2 设计决策**

1. **一元 RPC 而非双向流**：SendContext/StorageContext/GetSessionInfo 都是请求-响应模式，不需要流式传输。复用已有的 gRPC channel（Runner 已与 Host 建立连接）。
2. **plugin_id 由 Host 端注入**：RPC 请求中的 `plugin_id` 由 Host 端从 token 验证结果中获取，不信任 Runner 端传入的值（防止越权）。
3. **Storage per-plugin 隔离**：每个插件的存储数据独立 JSON 文件（`data/plugin_storage/{plugin_id}.json`），插件 A 无法访问插件 B 的数据。
4. **SendMessage 转发到 MessagePortV2**：不直接调用 send_service，通过核心 Protocol 接口解耦。

# **3. Proto 层设计**

## **3.1 新增消息定义**

在 `plugin_host.proto` 中新增以下消息和 RPC：

```protobuf
// ============================================================
// SDK 上下文 RPC（Phoenix-6）
// ============================================================

// ── SendMessage ──

message SendMessageRequest {
  string session_id = 1;
  string message_type = 2;  // TEXT/IMAGE/EMOJI/FORWARD/HYBRID
  string text_content = 3;
  string image_base64 = 4;
  string emoji_base64 = 5;
  string forward_message_id = 6;
  string hybrid_payload = 7;  // JSON
}

message SendMessageResponse {
  bool success = 1;
  string error = 2;  // SESSION_NOT_FOUND / SEND_FAILED / SCOPE_DENIED
  string message_id = 3;
}

// ── Storage ──

message StorageGetRequest {
  string key = 1;
  string default_value = 2;  // JSON 编码
}

message StorageGetResponse {
  bool found = 1;
  string value = 2;  // JSON 编码
  string error = 3;
}

message StorageSetRequest {
  string key = 1;
  string value = 2;  // JSON 编码
}

message StorageSetResponse {
  bool success = 1;
  string error = 2;
}

message StorageDeleteRequest {
  string key = 1;
}

message StorageDeleteResponse {
  bool deleted = 1;
  string error = 2;
}

// ── GetSessionInfo ──

message GetSessionInfoRequest {
  string session_id = 1;
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

## **3.2 新增 service 方法**

在 `PluginHost` service 中新增 5 个一元 RPC：

```protobuf
service PluginHost {
  rpc Connect(stream RunnerMessage) returns (stream HostMessage);
  rpc RegisterComponents(RegisterComponentsRequest) returns (RegisterComponentsResponse);
  // Phoenix-6: SDK 上下文 RPC
  rpc SendMessage(SendMessageRequest) returns (SendMessageResponse);
  rpc StorageGet(StorageGetRequest) returns (StorageGetResponse);
  rpc StorageSet(StorageSetRequest) returns (StorageSetResponse);
  rpc StorageDelete(StorageDeleteRequest) returns (StorageDeleteResponse);
  rpc GetSessionInfo(GetSessionInfoRequest) returns (GetSessionInfoResponse);
}
```

## **3.3 plugin_id 注入策略**

RPC 请求中**不包含** `plugin_id` 字段。Host 端通过 gRPC metadata 中的 `session_token` 验证身份，从 token 中提取 `plugin_id`。

理由：防止 Runner 伪造 plugin_id 越权访问其他插件的数据。

实现：Runner 端在调用 RPC 时，将 `session_token` 注入到 gRPC metadata 中：

```python
metadata = [("session_token", self._config.session_token)]
response = await stub.SendMessage(request, metadata=metadata)
```

Host 端在 RPC 方法中从 metadata 提取 token 并验证：

```python
def _resolve_plugin_id(self, context: grpc.aio.ServicerContext) -> str | None:
    metadata = dict(context.invocation_metadata())
    token = metadata.get("session_token", "")
    if self._token_service is not None:
        valid, plugin_id = self._token_service.validate_session(token)
        if valid:
            return plugin_id
    return None
```

### **3.3.1 TokenService.validate_session — 可重复验证**

**问题**：`TokenService.validate()` 是一次性的——验证后立即删除 token（L71 `del self._tokens[token]`）。SDK RPC 需要多次调用，第二次 validate 会失败。

**方案**：新增 `validate_session(token) -> tuple[bool, str]`，不删除 token，仅校验有效性：

```python
def validate_session(self, token: str) -> tuple[bool, str]:
    """可重复验证 session_token（不删除）。
    
    用于 SDK RPC 调用时的身份校验。
    Connect 握手仍用 validate()（一次性），SDK RPC 用 validate_session()（可重复）。
    """
    entry = self._tokens.get(token)
    if entry is None:
        return False, ""
    if entry.used:
        return False, ""
    if time.time() - entry.created_at > self._ttl:
        return False, ""
    return True, entry.plugin_id
```

**关键**：Connect 握手成功后，token 不被 validate_session 删除，SDK RPC 可反复使用。token 的生命周期由 `cleanup_expired()` 管理（TTL 默认 300 秒）。

# **4. Host 端实现**

## **4.1 SendMessage RPC**

```python
async def SendMessage(self, request, context):
    plugin_id = self._resolve_plugin_id(context)
    if plugin_id is None:
        return SendMessageResponse(success=False, error="AUTH_FAILED")
    
    # scope 校验
    if self._scope_store is not None:
        granted = self._scope_store.get_granted_scopes(plugin_id)
        required_scope = f"message:send:{request.message_type.lower()}"
        if required_scope not in granted:
            return SendMessageResponse(success=False, error="SCOPE_DENIED")
    
    # 转发到 MessagePortV2
    try:
        port = get_message_port()
        result = await port.send_message(
            session_id=request.session_id,
            text=request.text_content if request.message_type == "TEXT" else "",
            ...
        )
        return SendMessageResponse(success=True, message_id=result.message_id)
    except Exception as e:
        return SendMessageResponse(success=False, error="SEND_FAILED")
```

**关键**：Host 端通过 `get_message_port_v2()` 获取 MessagePortV2 实例（从注册点获取），不直接导入 send_service。

**SessionMessage 组装**：`MessagePortV2.send_message()` 接受 `SessionMessage` 对象，不是简单 text 参数。Host 端需要将 RPC 请求参数组装为 `SessionMessage`：

```python
from src.common.data_models.session_message_data_model import SessionMessage

msg = SessionMessage(
    session_id=request.session_id,
    message_type=request.message_type,
    # 按 message_type 填充对应字段
    text_content=request.text_content if request.message_type == "TEXT" else None,
    image_base64=request.image_base64 if request.message_type in ("IMAGE", "EMOJI") else None,
    ...
)
result = await port.send_message(msg)
```

具体 SessionMessage 字段需在编码时确认 `src/common/data_models/session_message_data_model.py` 的定义。

## **4.2 Storage RPC**

Host 端新增 `PerPluginStorage` 服务（`src/plugin_runtime_v2/host/storage_service.py`）：

```python
class PerPluginStorage:
    """Per-plugin JSON 文件存储。"""
    
    def __init__(self, base_dir: str = "data/plugin_storage") -> None:
        self._base_dir = base_dir
        self._data: dict[str, dict[str, Any]] = {}  # plugin_id → {key → value}
        self._load_all()
    
    def get(self, plugin_id: str, key: str, default: Any = None) -> Any:
        return self._data.get(plugin_id, {}).get(key, default)
    
    def set(self, plugin_id: str, key: str, value: Any) -> None:
        self._data.setdefault(plugin_id, {})[key] = value
        self._save(plugin_id)
    
    def delete(self, plugin_id: str, key: str) -> bool:
        store = self._data.get(plugin_id, {})
        if key in store:
            del store[key]
            self._save(plugin_id)
            return True
        return False
```

Storage RPC 实现调用 `PerPluginStorage`：

```python
async def StorageGet(self, request, context):
    plugin_id = self._resolve_plugin_id(context)
    if plugin_id is None:
        return StorageGetResponse(error="AUTH_FAILED")
    # scope 校验
    ...
    value = self._storage.get(plugin_id, request.key)
    ...
```

## **4.3 GetSessionInfo RPC**

```python
async def GetSessionInfo(self, request, context):
    plugin_id = self._resolve_plugin_id(context)
    if plugin_id is None:
        return GetSessionInfoResponse(error="AUTH_FAILED")
    # scope 校验
    ...
    port = get_session_repository()
    info = await port.get_session(request.session_id)
    if info is None:
        return GetSessionInfoResponse(error="SESSION_NOT_FOUND")
    return GetSessionInfoResponse(
        found=True, session_id=info.session_id,
        session_name=info.session_name, ...
    )
```

## **4.4 HostEndpoint 注入 storage_service**

在 `HostEndpoint.__init__` 中新增 `storage_service` 参数，传入 servicer。

在 `bootstrap.py` 中创建 `PerPluginStorage` 并注入。

# **5. Runner 端实现**

## **5.1 RunnerEndpoint 新增 RPC 客户端方法**

RunnerEndpoint 已持有 `self._channel`（与 Host 的 gRPC 通道）和 `self._config.session_token`。新增方法：

```python
async def send_message(self, session_id: str, message_type: str, **kwargs) -> dict[str, Any]:
    """通过 gRPC 调用 Host 的 SendMessage RPC。"""
    if self._channel is None:
        raise ConnectionError("Runner 未连接")
    stub = PluginHostStub(self._channel)
    request = plugin_host_pb2.SendMessageRequest(
        session_id=session_id, message_type=message_type, **kwargs,
    )
    metadata = [("session_token", self._config.session_token)]
    response = await stub.SendMessage(request, metadata=metadata)
    if not response.success:
        raise RuntimeError(f"SendMessage 失败: {response.error}")
    return {"message_id": response.message_id}

async def storage_get(self, key: str, default: Any = None) -> Any:
    """通过 gRPC 调用 Host 的 StorageGet RPC。"""
    ...

async def storage_set(self, key: str, value: Any) -> None:
    """通过 gRPC 调用 Host 的 StorageSet RPC。"""
    ...

async def storage_delete(self, key: str) -> bool:
    """通过 gRPC 调用 Host 的 StorageDelete RPC。"""
    ...

async def get_session_info(self, session_id: str) -> dict[str, Any]:
    """通过 gRPC 调用 Host 的 GetSessionInfo RPC。"""
    ...
```

## **5.2 SDK context 调用 RunnerEndpoint**

### SendContext

```python
async def text(self, session_id: str, text: str) -> dict[str, Any]:
    self._check_scope("text")
    return await self._runner.send_message(session_id, "TEXT", text_content=text)
```

5 个方法统一模式：scope 检查 → 调 `self._runner.send_message()` → 返回结果。

### StorageContext

```python
async def get(self, key: str, default: Any = None) -> Any:
    if "database:read:self" not in self._granted_scopes:
        raise ScopeDeniedError("Scope database:read:self 未授权")
    return await self._runner.storage_get(key, default)

async def set(self, key: str, value: Any) -> None:
    if "database:write:self" not in self._granted_scopes:
        raise ScopeDeniedError("Scope database:write:self 未授权")
    await self._runner.storage_set(key, value)

async def delete(self, key: str) -> bool:
    if "database:write:self" not in self._granted_scopes:
        raise ScopeDeniedError("Scope database:write:self 未授权")
    return await self._runner.storage_delete(key)
```

### PluginContext.get_session_info

```python
async def get_session_info(self, session_id: str) -> dict[str, Any]:
    self._check_scope("get_session_info", "session:read:detail")
    return await self._runner.get_session_info(session_id)
```

# **6. 新增文件清单**

| 文件 | 职责 |
|------|------|
| `src/plugin_runtime_v2/host/storage_service.py` | Per-plugin JSON 文件存储服务 |

# **7. 修改文件清单**

| 文件 | 改动 |
|------|------|
| `src/plugin_runtime_v2/proto/plugin_host.proto` | +5 个 RPC 方法 + 12 个消息类型 |
| `src/plugin_runtime_v2/host/servicer.py` | +5 个 RPC 实现 + `_resolve_plugin_id` |
| `src/plugin_runtime_v2/host/endpoint.py` | +storage_service 注入 |
| `src/plugin_runtime_v2/runner/endpoint.py` | +5 个 RPC 客户端方法 |
| `src/plugin_runtime_v2/sdk/context.py` | 9 个占位方法改为调用 RunnerEndpoint |
| `src/plugin_runtime_v2/bootstrap.py` | +PerPluginStorage 创建和注入 |

# **8. protoc 重新编译**

修改 `.proto` 后需重新编译生成 Python 代码：

```bash
docker exec maim-bot-core bash -c "cd /MaiMBot && python -m grpc_tools.protoc ..."
```

**重要**：每次 protoc 重新编译后，必须手动修正生成代码的 import 路径（Phoenix-0 已建立此规范）。

# **9. 风险与缓解**

| 风险 | 缓解 |
|------|------|
| gRPC channel 复用导致 RPC 调用与双向流冲突 | 一元 RPC 和双向流共享同一 channel 是 gRPC 标准用法，HTTP/2 多路复用天然支持 |
| plugin_id 伪造越权 | Host 端从 token 验证结果获取 plugin_id，不信任请求中的值 |
| Storage JSON 文件并发写入 | asyncio 单线程无并发问题；多进程场景需文件锁（当前单进程） |
| protoc 编译后 import 路径错误 | 手动修正（已有规范） |
| SendMessage 调 MessagePortV2 失败 | 返回 SEND_FAILED 错误，不重试（避免重复发送） |