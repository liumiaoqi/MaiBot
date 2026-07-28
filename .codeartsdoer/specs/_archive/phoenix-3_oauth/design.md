# Phoenix-3：OAuth Scope 授权 — 增量设计方案

# 一、需求与存量功能关系分析

## 1.1 需求功能与存量功能对比

### 1.1.1 已实现功能

| 需求功能 | 存量功能 | 代码位置 | 匹配度 |
|---------|---------|---------|--------|
| Scope 词汇表 | ScopeVocabulary（54 个 ScopeEntry + validate/lookup/map_capability） | `src/plugin_runtime_v2/scope/vocabulary.py:221-242` | 100% |
| Manifest v3 scopes 字段 | ManifestV3.scopes + _validate_scopes | `src/plugin_runtime_v2/sdk/manifest.py:69-80` | 100% |
| .proto session_token 字段 | HelloPayload.session_token + HelloResponse.rejected_scopes | `src/plugin_runtime_v2/proto/common.proto:38,48` | 100% |
| SDK 本地 scope 校验 | SendContext._check_scope + StorageContext + PluginContext._check_scope + ScopeDeniedError | `src/plugin_runtime_v2/sdk/context.py:15-169` | 100% |
| 握手必填校验 | _validate_hello 校验 session_token/scopes 非空 | `src/plugin_runtime_v2/host/servicer.py:230-244` | 50% |
| WebUI 插件路由 | /plugins 前缀，含 catalog/management/config/runtime 子路由 | `src/webui/routers/plugin/__init__.py` | 100% |

### 1.1.2 需要新建的功能

| 需求功能 | 存量功能 | 差异说明 | 新建方向 |
|---------|---------|---------|---------|
| Session Token 签发 | 无 | Phoenix-1 预留了字段但未实现签发逻辑 | 新建 TokenService |
| Scope 审批状态持久化 | 无 | 无任何审批状态存储 | 新建 ScopeApprovalStore |
| 握手阶段 Scope 校验 | _validate_hello 只校验非空 | 需验证 token 有效性 + 计算 granted/rejected scopes | 扩展 _validate_hello + Connect 流程 |
| Runner 端 granted_scopes 更新 | RunnerEndpointConfig.scopes 硬编码 | 需从 HelloResponse.rejected_scopes 计算 granted | 扩展 RunnerEndpoint._connect_and_handshake |
| WebUI Scope 审批 API | 无 | 无 scope 审批相关 API | 新建 scope_routes.py |
| WebUI Scope 审批页面 | 无 | 无 scope 审批前端组件 | 新建 Vue 组件 |

## 1.2 增量策略

Phoenix-3 采用**纯增量**策略：不修改已有代码的核心逻辑，只扩展调用点。

- **扩展点 1**：`_PluginHostServicer.__init__` 增加 `token_service` 和 `scope_store` 参数
- **扩展点 2**：`_validate_hello` 扩展 token 验证逻辑
- **扩展点 3**：`Connect` 方法在握手成功后计算 rejected_scopes
- **扩展点 4**：`RunnerEndpoint._connect_and_handshake` 处理 rejected_scopes
- **扩展点 5**：`HostEndpoint.__init__` 传递 token_service 和 scope_store
- **新建**：TokenService、ScopeApprovalStore、WebUI scope API + 页面

# 二、实现设计

## 2.1 服务/组件总体架构

```
src/plugin_runtime_v2/
├── scope/
│   ├── vocabulary.py          # [不变] Scope 词汇表
│   ├── token_service.py       # [新建] Session Token 签发/验证/清理
│   └── approval_store.py      # [新建] Scope 审批状态持久化
├── host/
│   ├── servicer.py            # [扩展] 握手时验证 token + 计算 granted/rejected
│   ├── endpoint.py            # [扩展] 传递 token_service + scope_store
│   └── ...
├── runner/
│   ├── endpoint.py            # [扩展] 处理 rejected_scopes，更新 granted_scopes
│   └── ...
└── sdk/
    └── context.py             # [不变] 本地 scope 校验已完整

src/webui/
├── routers/plugin/
│   ├── scope_routes.py        # [新建] Scope 审批 API
│   └── schemas.py             # [扩展] Scope 相关 schema
└── ...
```

## 2.2 TokenService

### 2.2.1 职责

签发、验证、清理一次性 session_token。Token 绑定 plugin_id，握手后立即失效。

### 2.2.2 接口

```python
class TokenService:
    def __init__(self, ttl_seconds: int = 300) -> None: ...
    def issue(self, plugin_id: str) -> str: ...
    def validate(self, token: str) -> tuple[bool, str]:
        """返回 (valid, plugin_id)。验证后立即删除 token。"""
    def cleanup_expired(self) -> int: ...
```

### 2.2.3 存储模型

内存 dict，key=token，value=`_TokenEntry(plugin_id, created_at, used)`。

- `issue`：`secrets.token_urlsafe(32)` 生成，存入 dict
- `validate`：查找 token → 检查 used=False + 未过期 → 标记 used=True → 返回 plugin_id
- `cleanup_expired`：遍历删除 `created_at + ttl < now` 的条目，定期调用（如每 60 秒）

### 2.2.4 线程安全

Python asyncio 单线程模型，dict 操作无需加锁。`cleanup_expired` 由 asyncio 定时任务调用。

### 2.2.5 Token 签发入口

Token 签发通过 **WebUI API** 触发。管理员在 WebUI 安装插件或为插件生成连接凭证时，调用签发 API 获取 session_token，将其传递给 Runner 启动配置。

签发 API 路由：

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/plugins/{plugin_id}/token` | 为指定插件签发一次性 session_token |

Runner 启动流程：
1. 管理员通过 WebUI 生成 token
2. 将 token 写入 Runner 的配置文件（`bot_config.toml` 或环境变量）
3. Runner 启动时携带 token 连接 Host

Host 重启时所有未使用 token 丢失——Runner 需重新获取。这是可接受的，因为 token 是一次性的，与连接生命周期绑定。

### 2.2.6 cleanup_expired 定时任务

在 `HostEndpoint.start()` 中启动 `asyncio.create_task` 定时清理过期 token，`stop()` 中取消。

## 2.3 ScopeApprovalStore

### 2.3.1 职责

管理每个 plugin_id 的已批准 scope 集合，持久化到 JSON 文件。

### 2.3.2 接口

```python
class ScopeApprovalStore:
    def __init__(self, file_path: str) -> None: ...
    def get_granted_scopes(self, plugin_id: str) -> set[str]: ...
    def approve_scope(self, plugin_id: str, scope: str, operator: str = "user") -> None: ...
    def revoke_scope(self, plugin_id: str, scope: str, operator: str = "user") -> None: ...
    def approve_all_pending(self, plugin_id: str, requested_scopes: list[str]) -> int: ...
    def get_all_approvals(self) -> dict[str, set[str]]: ...
    def save(self) -> None: ...
    def load(self) -> None: ...
```

### 2.3.3 存储模型

JSON 文件 `data/plugin_runtime_v2/scope_approvals.json`：

```json
{
  "version": 1,
  "updated_at": 1721923200,
  "approvals": {
    "org.plugin_a": {
      "granted_scopes": ["message:send:text", "database:read:self"],
      "updated_at": 1721923100,
      "updated_by": "user"
    }
  }
}
```

### 2.3.4 自动批准逻辑

`get_granted_scopes` 返回已批准的 scope 集合。当插件首次请求 scope 时：

1. 查找 ScopeEntry，`approval_required=False` 的 scope 自动加入 granted_scopes
2. `approval_required=True` 的 scope 需用户显式批准

此逻辑在 `approve_all_pending` 中实现：遍历 requested_scopes，对 `approval_required=False` 的自动调用 `approve_scope(operator="system")`。

### 2.3.5 词汇表清理

`load` 时遍历 granted_scopes，移除 `ScopeVocabulary.validate(s) == False` 的条目，记录 WARNING 日志。

## 2.4 握手流程扩展

### 2.4.1 _validate_hello 扩展

```python
def _validate_hello(self, hello):
    # ... 现有校验 ...
    # 新增：验证 session_token
    if self._token_service is not None:
        valid, plugin_id = self._token_service.validate(hello.session_token)
        if not valid:
            return False, "TOKEN_INVALID"
    return True, ""
```

### 2.4.2 Connect 方法扩展

握手成功后，计算 rejected_scopes：

```python
# 在 yield HelloResponse 之前
if self._scope_store is not None:
    approved = self._scope_store.get_granted_scopes(plugin_id)
    # 自动批准 approval_required=False 的 scope
    self._scope_store.approve_all_pending(plugin_id, list(hello.scopes))
    approved = self._scope_store.get_granted_scopes(plugin_id)
    requested = set(hello.scopes)
    rejected = requested - approved
    rejected_scopes = list(rejected)
    granted_scopes = requested & approved
else:
    rejected_scopes = []
    granted_scopes = set(hello.scopes)

yield HelloResponse(accepted=True, host_version=host_ver, rejected_scopes=rejected_scopes)
```

### 2.4.3 RunnerConnection 扩展

`RunnerConnection.scopes` 改为存储 granted_scopes（而非 requested_scopes），确保后续逻辑只使用已批准的 scope。

## 2.5 Runner 端 granted_scopes 更新

### 2.5.1 _connect_and_handshake 扩展

```python
hr = first_response.hello_response
if hr.accepted and hr.rejected_scopes:
    # 从 config.scopes 中移除被拒绝的 scope
    original = set(self._config.scopes)
    rejected = set(hr.rejected_scopes)
    self._granted_scopes = original - rejected
    logger.warning("部分 scope 被拒绝: %s", hr.rejected_scopes)
else:
    self._granted_scopes = set(self._config.scopes)
```

### 2.5.2 PluginContext granted_scopes 更新

RunnerEndpoint 在创建 PluginContext 时，使用 `self._granted_scopes` 替代 `set(self._config.scopes)`：

```python
ctx = PluginContext(
    plugin_id=self._config.plugin_id,
    granted_scopes=self._granted_scopes,  # 改为实际批准的 scope
    runner_endpoint=self,
    homecard_registry=homecard_registry,
)
```

## 2.6 WebUI Scope 审批 API

### 2.6.1 路由设计

在 `src/webui/routers/plugin/scope_routes.py` 新建，挂载到 `/plugins` 前缀下：

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/plugins/scopes` | 所有插件的 scope 审批概览 |
| GET | `/plugins/{plugin_id}/scopes` | 某插件的 scope 详情（按资源域分组） |
| POST | `/plugins/{plugin_id}/scopes/{scope}/approve` | 批准单个 scope |
| POST | `/plugins/{plugin_id}/scopes/{scope}/revoke` | 撤销单个 scope |
| POST | `/plugins/{plugin_id}/scopes/approve-all` | 批量批准所有待审批 scope |

### 2.6.2 Schema 设计

```python
class ScopeStatus(str, Enum):
    GRANTED = "granted"
    PENDING = "pending"
    REVOKED = "revoked"

class ScopeDetail(BaseModel):
    scope: str
    description: str
    risk_level: str
    approval_required: bool
    status: ScopeStatus

class PluginScopeOverview(BaseModel):
    plugin_id: str
    total: int
    granted: int
    pending: int

class PluginScopeDetail(BaseModel):
    plugin_id: str
    scopes: dict[str, list[ScopeDetail]]  # key=资源域
```

### 2.6.3 插件发现机制

Scope 审批 API 需要列出"已安装插件及其 Manifest scopes"。Phoenix-3 阶段采用**简化发现机制**：

1. 扫描 `plugins/` 目录下所有子目录
2. 读取每个子目录中的 `_manifest.json`（ManifestV3 格式）
3. 提取 `id` 和 `scopes` 字段
4. 解析失败的插件跳过并记录 WARNING

此机制不依赖 v1 的 `src/plugin_runtime/` 或 v2 的注册表，直接从文件系统发现。后续 Phoenix-4 可替换为更完善的插件注册表查询。

### 2.6.4 ScopeApprovalStore 注入

Scope 审批 API 需要访问 ScopeApprovalStore。通过 FastAPI 依赖注入：

1. 在应用启动时创建 ScopeApprovalStore 实例
2. 通过 `app.state.scope_store` 存储
3. API 路由通过 `Depends` 获取

## 2.7 数据模型

### 2.7.1 _TokenEntry

```python
@dataclass(slots=True)
class _TokenEntry:
    plugin_id: str
    created_at: float
    used: bool = False
```

### 2.7.2 ScopeApprovalFile

```json
{
  "version": 1,
  "updated_at": 1721923200,
  "approvals": {
    "org.plugin_name": {
      "granted_scopes": ["message:send:text"],
      "updated_at": 1721923100,
      "updated_by": "user"
    }
  }
}
```

### 2.7.3 设计目标

1. **人类可读**：JSON 格式，支持手动编辑
2. **原子写入**：先写临时文件再 rename，防止写入中断导致数据丢失
3. **增量更新**：每次 approve/revoke 后立即持久化，不依赖定时保存
4. **词汇表兼容**：加载时自动清理词汇表中已删除的 scope

# 三、文件变更清单

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `src/plugin_runtime_v2/scope/token_service.py` | 新建 | TokenService 实现 |
| `src/plugin_runtime_v2/scope/approval_store.py` | 新建 | ScopeApprovalStore 实现 |
| `src/plugin_runtime_v2/host/servicer.py` | 扩展 | _validate_hello 增加 token 验证；Connect 增加 scope 校验 + rejected_scopes |
| `src/plugin_runtime_v2/host/endpoint.py` | 扩展 | HostEndpoint 构造增加 token_service + scope_store 参数 |
| `src/plugin_runtime_v2/runner/endpoint.py` | 扩展 | 处理 rejected_scopes，PluginContext 使用 granted_scopes |
| `src/webui/routers/plugin/scope_routes.py` | 新建 | Scope 审批 API + Token 签发 API |
| `src/webui/routers/plugin/schemas.py` | 扩展 | Scope 相关 schema |
| `src/webui/routers/plugin/__init__.py` | 扩展 | 注册 scope_routes |
| `src/plugin_runtime_v2/host/endpoint.py` | 扩展 | start() 启动 cleanup_expired 定时任务，stop() 取消 |