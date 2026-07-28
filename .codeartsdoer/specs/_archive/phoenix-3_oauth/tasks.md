# Phoenix-3：OAuth Scope 授权 — 编码任务

# 任务依赖关系

```
T1(TokenService) ──→ T3(握手扩展) ──→ T5(Runner granted_scopes)
T2(ApprovalStore) ──→ T3(握手扩展)
T2(ApprovalStore) ──→ T4(WebUI API)
T1(TokenService) ──→ T4(WebUI API)
T4(WebUI API) ──→ T6(集成测试)
T3(握手扩展) ──→ T6(集成测试)
T5(Runner granted_scopes) ──→ T6(集成测试)
```

# T1: TokenService — Session Token 签发/验证/清理

## 依赖
无

## 子任务

- [ ] T1.1: 创建 `src/plugin_runtime_v2/scope/token_service.py`，实现 `TokenService` 类
  - `__init__(self, ttl_seconds: int = 300)`：初始化 token 存储字典和 TTL
  - `issue(self, plugin_id: str) -> str`：使用 `secrets.token_urlsafe(32)` 生成 token，存入 `_TokenEntry(plugin_id, time.time(), used=False)`，返回 token
  - `validate(self, token: str) -> tuple[bool, str]`：查找 token → 检查 used=False + 未过期 → 标记 used=True → 返回 `(True, plugin_id)`；失败返回 `(False, "")`
  - `cleanup_expired(self) -> int`：遍历删除 `created_at + ttl < time.time()` 的条目，返回清理数量
  - `_TokenEntry` dataclass：`plugin_id: str, created_at: float, used: bool = False`
- [ ] T1.2: 编写 `tests/plugin_runtime_v2/scope/test_token_service.py`
  - test_issue_returns_valid_token：签发 token 长度 ≥43
  - test_validate_success：签发后验证返回 (True, plugin_id)
  - test_validate_consumed：验证后再次验证返回 (False, "")
  - test_validate_expired：修改 created_at 使其过期，验证返回 (False, "")
  - test_validate_unknown：验证不存在的 token 返回 (False, "")
  - test_cleanup_expired：签发多个 token，部分过期，cleanup 清理正确数量

## 验收标准
- ruff check 通过
- 6 个单元测试全部通过

---

# T2: ScopeApprovalStore — 审批状态持久化

## 依赖
无

## 子任务

- [ ] T2.1: 创建 `src/plugin_runtime_v2/scope/approval_store.py`，实现 `ScopeApprovalStore` 类
  - `__init__(self, file_path: str)`：初始化文件路径和内存缓存
  - `load(self) -> None`：从 JSON 文件加载审批状态；文件不存在则初始化空状态；加载时清理词汇表中已删除的 scope
  - `save(self) -> None`：原子写入 JSON 文件（先写临时文件再 rename）
  - `get_granted_scopes(self, plugin_id: str) -> set[str]`：返回已批准的 scope 集合
  - `approve_scope(self, plugin_id: str, scope: str, operator: str = "user") -> None`：批准 scope，记录审计日志，save
  - `revoke_scope(self, plugin_id: str, scope: str, operator: str = "user") -> None`：撤销 scope，记录审计日志，save
  - `approve_all_pending(self, plugin_id: str, requested_scopes: list[str]) -> int`：遍历 requested_scopes，对 `approval_required=False` 的自动调用 approve_scope(operator="system")，返回自动批准数量
  - `get_all_approvals(self) -> dict[str, set[str]]`：返回所有插件的审批状态
- [ ] T2.2: 编写 `tests/plugin_runtime_v2/scope/test_approval_store.py`
  - test_approve_and_get：批准 scope 后查询返回正确集合
  - test_revoke：撤销 scope 后查询不包含该 scope
  - test_auto_approve_low_risk：approval_required=False 的 scope 自动批准
  - test_persistence：批准 → save → 重新 load → scope 仍为已批准
  - test_vocab_cleanup：加载时自动清理词汇表不存在的 scope
  - test_file_not_found：文件不存在时以空状态初始化
  - test_file_corrupted：文件格式错误时以空状态初始化并记录 WARNING

## 验收标准
- ruff check 通过
- 7 个单元测试全部通过

---

# T3: 握手流程扩展 — Token 验证 + Scope 校验

## 依赖
T1, T2

## 子任务

- [ ] T3.1: 修改 `src/plugin_runtime_v2/host/servicer.py`
  - `_PluginHostServicer.__init__` 增加 `token_service: TokenService | None = None` 和 `scope_store: ScopeApprovalStore | None = None` 参数
  - `_validate_hello` 增加 token 验证：调用 `self._token_service.validate(hello.session_token)`，无效返回 `(False, "TOKEN_INVALID")`；验证成功后保存 plugin_id 供后续使用
  - `Connect` 方法在握手成功后计算 rejected_scopes：调用 `self._scope_store.approve_all_pending(plugin_id, list(hello.scopes))` 自动批准低风险 scope，然后计算 `granted = requested ∩ approved`，`rejected = requested - approved`，写入 HelloResponse.rejected_scopes
  - `Connect` 方法将 granted_scopes（而非 requested_scopes）存入 RunnerConnection.scopes
- [ ] T3.2: 修改 `src/plugin_runtime_v2/host/endpoint.py`
  - `HostEndpoint.__init__` 增加 `token_service=None, scope_store=None` 参数
  - 传递给 `_PluginHostServicer` 构造
  - `start()` 中启动 cleanup_expired 定时任务：`asyncio.create_task(self._cleanup_loop())`
  - `stop()` 中取消定时任务
- [ ] T3.3: 编写 `tests/plugin_runtime_v2/host/test_handshake_scope.py`
  - test_valid_token_accepted：有效 token + 已批准 scope → accepted=true, rejected_scopes=[]
  - test_invalid_token_rejected：无效 token → accepted=false, reason="TOKEN_INVALID"
  - test_partial_scope_rejected：部分 scope 未批准 → accepted=true, rejected_scopes 非空
  - test_auto_approve_low_risk：低风险 scope 自动批准
  - test_no_scope_store_fallback：scope_store=None 时所有 scope 默认通过

## 验收标准
- ruff check 通过
- 5 个单元测试全部通过
- Phoenix-1/2 已有测试不受影响

---

# T4: WebUI Scope 审批 API

## 依赖
T2, T1

## 子任务

- [ ] T4.1: 扩展 `src/webui/routers/plugin/schemas.py`
  - 新增 `ScopeStatus` 枚举（granted/pending/revoked）
  - 新增 `ScopeDetail` 模型（scope/description/risk_level/approval_required/status）
  - 新增 `PluginScopeOverview` 模型（plugin_id/total/granted/pending）
  - 新增 `PluginScopeDetail` 模型（plugin_id/scopes: dict[str, list[ScopeDetail]]）
- [ ] T4.2: 创建 `src/webui/routers/plugin/scope_routes.py`
  - `GET /plugins/scopes`：调用 `scope_store.get_all_approvals()` + 扫描 `plugins/` 目录下 `_manifest.json` 获取插件列表和 scope 声明，返回概览列表
  - `GET /plugins/{plugin_id}/scopes`：查询该插件的审批状态 + Manifest 中声明的 scope，按资源域分组返回
  - `POST /plugins/{plugin_id}/scopes/{scope}/approve`：调用 `scope_store.approve_scope()`
  - `POST /plugins/{plugin_id}/scopes/{scope}/revoke`：调用 `scope_store.revoke_scope()`
  - `POST /plugins/{plugin_id}/scopes/approve-all`：调用 `scope_store.approve_all_pending()`
  - `POST /plugins/{plugin_id}/token`：调用 `token_service.issue(plugin_id)` 签发一次性 session_token，返回 `{"token": "xxx", "ttl_seconds": 300}`
  - 插件发现机制：扫描 `plugins/` 目录下所有子目录，读取 `_manifest.json`（ManifestV3 格式），提取 `id` 和 `scopes`；解析失败跳过并记录 WARNING
- [ ] T4.3: 修改 `src/webui/routers/plugin/__init__.py`
  - 注册 scope_routes
- [ ] T4.4: ScopeApprovalStore + TokenService 注入
  - 在 WebUI 应用启动时创建 ScopeApprovalStore 实例和 TokenService 实例
  - 通过 `app.state.scope_store` 和 `app.state.token_service` 存储
  - API 路由通过 `Request.app.state.scope_store` / `Request.app.state.token_service` 获取

## 验收标准
- ruff check 通过
- API 路由可通过 FastAPI TestClient 测试

---

# T5: Runner 端 granted_scopes 更新

## 依赖
T3

## 子任务

- [ ] T5.1: 修改 `src/plugin_runtime_v2/runner/endpoint.py`
  - 新增 `self._granted_scopes: set[str]` 属性，初始为 `set(self._config.scopes)`
  - `_connect_and_handshake` 中处理 HelloResponse.rejected_scopes：从 `_granted_scopes` 中移除被拒绝的 scope
  - 创建 PluginContext 时使用 `self._granted_scopes` 替代 `set(self._config.scopes)`
- [ ] T5.2: 编写 `tests/plugin_runtime_v2/runner/test_granted_scopes.py`
  - test_no_rejected_scopes：rejected_scopes 为空 → granted_scopes 等于 config.scopes
  - test_partial_rejected：部分 scope 被拒绝 → granted_scopes 正确排除
  - test_all_rejected：所有 scope 被拒绝 → granted_scopes 为空集

## 验收标准
- ruff check 通过
- 3 个单元测试全部通过

---

# T6: 集成测试

## 依赖
T3, T4, T5

## 子任务

- [ ] T6.1: 编写 `tests/plugin_runtime_v2/test_phoenix3_e2e.py`
  - test_full_scope_lifecycle：签发 token → 握手（低风险自动批准）→ Runner 获得 granted_scopes → 调用 SDK 方法不抛 ScopeDeniedError
  - test_high_risk_scope_requires_approval：高风险 scope 未批准 → 握手后 rejected → SDK 调用抛 ScopeDeniedError
  - test_approve_then_reconnect：WebUI 批准 scope → Runner 重连 → 获得 expanded granted_scopes
  - test_revoke_then_reconnect：WebUI 撤销 scope → Runner 重连 → granted_scopes 缩减
  - test_token_reuse_rejected：同一 token 第二次握手 → 被拒绝

## 验收标准
- ruff check 通过
- 5 个集成测试全部通过
- Phoenix-1/2 已有 52 个测试全部通过（无回归）