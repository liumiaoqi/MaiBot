# Phoenix-6：SDK RPC 通道 — 编码任务

> 依赖：Phoenix-0~5 全部完成
> 核心交付：9 个 SDK 占位方法变为真实 RPC 通道 + 5 个新 RPC + PerPluginStorage

---

## T0：TokenService 修正（阻塞项）

### T0.1：TokenService 新增 validate_session 方法

**文件**：`src/plugin_runtime_v2/scope/token_service.py`

新增 `validate_session(self, token: str) -> tuple[bool, str]`：
- 与 `validate()` 逻辑相同，但**不删除 token**
- 用于 SDK RPC 调用时的可重复身份校验
- Connect 握手仍用 `validate()`（一次性），SDK RPC 用 `validate_session()`（可重复）

**原因**：当前 `validate()` L71 `del self._tokens[token]` 是一次性使用。SDK RPC 需要多次调用，第二次 validate 会失败。

验证：`python -c "from src.plugin_runtime_v2.scope.token_service import TokenService; ts = TokenService(); t = ts.issue('p1'); print(ts.validate_session(t)); print(ts.validate_session(t))"` 输出两行 `(True, 'p1')`

---

## T1：Proto 层扩展

### T1.1：plugin_host.proto 新增 5 个 RPC + 12 个消息类型

**文件**：`src/plugin_runtime_v2/proto/plugin_host.proto`

1. 在 `service PluginHost` 中新增 5 个一元 RPC：
   - `rpc SendMessage(SendMessageRequest) returns (SendMessageResponse);`
   - `rpc StorageGet(StorageGetRequest) returns (StorageGetResponse);`
   - `rpc StorageSet(StorageSetRequest) returns (StorageSetResponse);`
   - `rpc StorageDelete(StorageDeleteRequest) returns (StorageDeleteResponse);`
   - `rpc GetSessionInfo(GetSessionInfoRequest) returns (GetSessionInfoResponse);`

2. 新增 12 个消息类型（定义在 service 之前）：
   - `SendMessageRequest`：session_id, message_type, text_content, image_base64, emoji_base64, forward_message_id, hybrid_payload
   - `SendMessageResponse`：success, error, message_id
   - `StorageGetRequest`：key, default_value
   - `StorageGetResponse`：found, value, error
   - `StorageSetRequest`：key, value
   - `StorageSetResponse`：success, error
   - `StorageDeleteRequest`：key
   - `StorageDeleteResponse`：deleted, error
   - `GetSessionInfoRequest`：session_id
   - `GetSessionInfoResponse`：found, session_id, session_name, platform, is_group_session, primary_agent_id, error

**注意**：请求消息中**不包含** plugin_id 字段（Host 端从 token 验证获取）。

验证：`grep "rpc SendMessage\|rpc StorageGet\|rpc StorageSet\|rpc StorageDelete\|rpc GetSessionInfo" src/plugin_runtime_v2/proto/plugin_host.proto` 返回 5 行

### T1.2：protoc 重新编译 + 修正 import

**操作**：在 Docker 中重新编译 proto 文件

```bash
docker exec maim-bot-core bash -c "cd /MaiMBot && python -m grpc_tools.protoc -I src/plugin_runtime_v2/proto --python_out=src/plugin_runtime_v2/proto --grpc_python_out=src/plugin_runtime_v2/proto src/plugin_runtime_v2/proto/common.proto src/plugin_runtime_v2/proto/plugin_host.proto src/plugin_runtime_v2/proto/plugin_runner.proto"
```

**重要**：编译后手动修正生成代码的 import 路径（Phoenix-0 规范）。具体修正：
- `plugin_host_pb2_grpc.py` 中的 `import plugin_host_pb2` → `from src.plugin_runtime_v2.proto import plugin_host_pb2`
- 同理修正 `plugin_host_pb2_grpc.py` 中的 `import common_pb2` → `from src.plugin_runtime_v2.proto import common_pb2`

验证：`python -c "from src.plugin_runtime_v2.proto.plugin_host_pb2_grpc import PluginHostServicer"` 不报错

---

## T2：Host 端实现

### T2.1：新增 PerPluginStorage

**文件**：`src/plugin_runtime_v2/host/storage_service.py`（新建）

实现 `PerPluginStorage` 类：
- `__init__(self, base_dir: str = "data/plugin_storage")` — 初始化，加载已有数据
- `get(self, plugin_id: str, key: str, default: Any = None) -> Any` — 读取
- `set(self, plugin_id: str, key: str, value: Any) -> None` — 写入 + 持久化
- `delete(self, plugin_id: str, key: str) -> bool` — 删除 + 持久化
- `_load_all(self) -> None` — 启动时加载所有 JSON 文件
- `_save(self, plugin_id: str) -> None` — 写入单个插件的 JSON 文件

每个插件一个 JSON 文件：`{base_dir}/{plugin_id}.json`。

验证：`python -c "from src.plugin_runtime_v2.host.storage_service import PerPluginStorage; s = PerPluginStorage(); s.set('test', 'k', 'v'); print(s.get('test', 'k'))"` 输出 `v`

### T2.2：servicer.py 新增 _resolve_plugin_id

**文件**：`src/plugin_runtime_v2/host/servicer.py`

新增辅助方法：

```python
def _resolve_plugin_id(self, context: grpc.aio.ServicerContext) -> str | None:
    """从 gRPC metadata 的 session_token 中解析 plugin_id。"""
    metadata = dict(context.invocation_metadata())
    token = metadata.get("session_token", "")
    if self._token_service is not None and token:
        valid, plugin_id = self._token_service.validate_session(token)
        if valid:
            return plugin_id
    return None
```

验证：`grep "_resolve_plugin_id" src/plugin_runtime_v2/host/servicer.py` 返回匹配

### T2.3：servicer.py 新增 _check_scope 辅助

**文件**：`src/plugin_runtime_v2/host/servicer.py`

新增 scope 校验辅助方法：

```python
def _check_scope(self, plugin_id: str, scope: str) -> bool:
    """检查插件是否拥有指定 scope。"""
    if self._scope_store is None:
        return False
    granted = self._scope_store.get_granted_scopes(plugin_id)
    return scope in granted
```

验证：`grep "_check_scope" src/plugin_runtime_v2/host/servicer.py` 返回匹配

### T2.4：servicer.py 实现 5 个 RPC

**文件**：`src/plugin_runtime_v2/host/servicer.py`

1. **SendMessage**：
   - `_resolve_plugin_id` → 认证失败返回 `AUTH_FAILED`
   - `_check_scope(plugin_id, f"message:send:{request.message_type.lower()}")` → `SCOPE_DENIED`
   - **组装 SessionMessage**：`MessagePortV2.send_message()` 接受 `SessionMessage` 对象，不是简单 text。需要将 RPC 请求参数组装为 `SessionMessage`（确认 `src/common/data_models/session_message_data_model.py` 的字段定义后构造）
   - 调用 `MessagePortV2.send_message(session_msg)` → 成功返回 `message_id`，失败返回 `SEND_FAILED`
   - MessagePortV2 从 `src.core.message_port_registry.get_message_port_v2()` 获取

2. **StorageGet**：
   - 认证 + `_check_scope(plugin_id, "database:read:self")`
   - 调用 `self._storage.get(plugin_id, key, default)`

3. **StorageSet**：
   - 认证 + `_check_scope(plugin_id, "database:write:self")`
   - 调用 `self._storage.set(plugin_id, key, value)`

4. **StorageDelete**：
   - 认证 + `_check_scope(plugin_id, "database:write:self")`
   - 调用 `self._storage.delete(plugin_id, key)`

5. **GetSessionInfo**：
   - 认证 + `_check_scope(plugin_id, "session:read:detail")`
   - 调用 `SessionRepository.get_session()` → 成功返回快照，不存在返回 `SESSION_NOT_FOUND`
   - SessionRepository 从 `src.core.session_port_registry.get_session_lifecycle_port()` 或 `get_session_info_port()` 获取

验证：`grep "async def SendMessage\|async def StorageGet\|async def StorageSet\|async def StorageDelete\|async def GetSessionInfo" src/plugin_runtime_v2/host/servicer.py` 返回 5 行

### T2.5：HostEndpoint 注入 storage_service

**文件**：`src/plugin_runtime_v2/host/endpoint.py`

1. `HostEndpoint.__init__` 新增 `storage_service=None` 参数
2. 传入 servicer：`_PluginHostServicer(..., storage_service=storage_service)`
3. 存储 `self._storage_service = storage_service`

**文件**：`src/plugin_runtime_v2/bootstrap.py`

在 `init_v2_host_endpoint` 中创建 `PerPluginStorage` 并注入 HostEndpoint。

验证：`grep "storage_service" src/plugin_runtime_v2/host/endpoint.py` 返回匹配

---

## T3：Runner 端实现

### T3.1：RunnerEndpoint 新增 5 个 RPC 客户端方法

**文件**：`src/plugin_runtime_v2/runner/endpoint.py`

新增 5 个方法，统一模式：创建 stub → 构造 request → 注入 metadata → 调用 RPC → 处理响应

1. `async def send_message(self, session_id, message_type, **kwargs) -> dict` — 调 SendMessage
2. `async def storage_get(self, key, default=None) -> Any` — 调 StorageGet
3. `async def storage_set(self, key, value) -> None` — 调 StorageSet
4. `async def storage_delete(self, key) -> bool` — 调 StorageDelete
5. `async def get_session_info(self, session_id) -> dict` — 调 GetSessionInfo

关键实现细节：
- 使用 `PluginHostStub(self._channel)` 创建 stub（channel 已在 `_connect_and_handshake` 中创建）
- metadata 注入 `session_token`：`metadata = [("session_token", self._config.session_token)]`
- 失败时抛出 `RuntimeError` 或返回错误信息

**注意**：channel 可能在重连期间为 None，需检查 `self._channel is not None`。

验证：`grep "async def send_message\|async def storage_get\|async def storage_set\|async def storage_delete\|async def get_session_info" src/plugin_runtime_v2/runner/endpoint.py` 返回 5 行

---

## T4：SDK context 实现

### T4.1：SendContext 5 个方法改为调用 RPC

**文件**：`src/plugin_runtime_v2/sdk/context.py`

将 5 个占位方法改为调用 `self._runner.send_message()`：

```python
async def text(self, session_id: str, text: str) -> dict[str, Any]:
    self._check_scope("text")
    return await self._runner.send_message(session_id, "TEXT", text_content=text)

async def image(self, session_id: str, image_base64: str) -> dict[str, Any]:
    self._check_scope("image")
    return await self._runner.send_message(session_id, "IMAGE", image_base64=image_base64)

async def emoji(self, session_id: str, emoji_base64: str) -> dict[str, Any]:
    self._check_scope("emoji")
    return await self._runner.send_message(session_id, "EMOJI", emoji_base64=emoji_base64)

async def forward(self, session_id: str, message_id: str) -> dict[str, Any]:
    self._check_scope("forward")
    return await self._runner.send_message(session_id, "FORWARD", forward_message_id=message_id)

async def hybrid(self, session_id: str, segments: list[dict[str, Any]]) -> dict[str, Any]:
    self._check_scope("hybrid")
    import json
    return await self._runner.send_message(session_id, "HYBRID", hybrid_payload=json.dumps(segments))
```

验证：`grep "TODO.*Phoenix-4.*RPC" src/plugin_runtime_v2/sdk/context.py` 返回 0 行（所有占位注释已移除）

### T4.2：StorageContext 3 个方法改为调用 RPC

**文件**：`src/plugin_runtime_v2/sdk/context.py`

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

验证：`grep "TODO.*Phoenix-4.*RPC" src/plugin_runtime_v2/sdk/context.py` 返回 0 行

### T4.3：PluginContext.get_session_info 改为调用 RPC

**文件**：`src/plugin_runtime_v2/sdk/context.py`

```python
async def get_session_info(self, session_id: str) -> dict[str, Any]:
    self._check_scope("get_session_info", "session:read:detail")
    return await self._runner.get_session_info(session_id)
```

验证：`grep "TODO.*Phoenix-4.*RPC" src/plugin_runtime_v2/sdk/context.py` 返回 0 行

---

## T5：测试

### T5.1：PerPluginStorage 单元测试

**文件**：`tests/plugin_runtime_v2/test_storage_service.py`（新建）

- set + get 正常工作
- get 不存在的 key 返回 default
- delete 后 get 返回 default
- per-plugin 隔离（插件 A 的数据插件 B 不可见）
- 持久化（set 后重新加载仍可读取）

### T5.2：SDK context RPC 集成测试

**文件**：`tests/plugin_runtime_v2/test_sdk_rpc.py`（新建）

- SendContext.text() 通过 RPC 发送消息
- StorageContext get/set/delete 通过 RPC 工作
- PluginContext.get_session_info 通过 RPC 查询
- scope 不足时抛出 ScopeDeniedError
- 未认证时返回 AUTH_FAILED

### T5.3：Host servicer RPC 测试

**文件**：`tests/plugin_runtime_v2/test_host_sdk_rpc.py`（新建）

- SendMessage RPC 认证 + scope 校验 + 转发
- StorageGet/Set/Delete RPC 认证 + scope 校验
- GetSessionInfo RPC 认证 + scope 校验
- 无 token 时返回 AUTH_FAILED
- scope 不足时返回 SCOPE_DENIED

---

## 任务依赖与执行顺序

```
T0 (TokenService修正) ──→ T2 (Host) ──→ T4 (SDK context) ──→ T5 (测试)
                              ↑
T1 (Proto) ──────────────────┘
     │
     └──────────────────────→ T3 (Runner) ──→ T4
```

推荐执行顺序：**T0 → T1 → T2 → T3 → T4 → T5**

## 派发建议

| 任务 | 负责人 | 理由 |
|------|--------|------|
| T0.1 TokenService.validate_session | CC | 需理解一次性 token 设计意图 |
| T1.1 Proto 定义 | CC | 首次设计消息结构 |
| T1.2 protoc 编译 | CC | 需手动修正 import 路径 |
| T2.1 PerPluginStorage | Codex | 独立模块，接口明确 |
| T2.2-T2.4 Host servicer | CC | 需理解 Protocol 接口 + token 验证 + scope 校验 + SessionMessage 组装 |
| T2.5 注入 | Codex | 机械修改 |
| T3.1 RunnerEndpoint | CC | 需理解 gRPC stub + metadata 注入 |
| T4.1-T4.3 SDK context | Codex | 机械替换占位实现 |
| T5.1-T5.3 测试 | CC | 集成测试需理解完整链路 |