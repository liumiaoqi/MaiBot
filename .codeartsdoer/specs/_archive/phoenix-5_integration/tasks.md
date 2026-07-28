# Phoenix-5：v2 主程序集成 — 编码任务

> 依赖：Phoenix-0~4 全部完成
> 核心交付：v2 HostEndpoint 接入 main.py 生命周期 + Scope 审批 WebUI 激活 + 重复子目录清理 + Runner 进程管理 + per-plugin 速率限制

---

## T1：Protocol 层 + 配置层 — 基础设施

### T1.1：AppConfigPort 新增 8 个 v2 方法

**文件**：`src/core/protocols.py`

在 `AppConfigPort` 的 `=== Plugin Runtime 域 ===` 分组下新增：

```python
# === Plugin Runtime V2 域 ===
def get_plugin_runtime_v2_enabled(self) -> bool: ...
def get_plugin_runtime_v2_host_listen_address(self) -> str: ...
def get_plugin_runtime_v2_runner_spawn_count(self) -> int: ...
def get_plugin_runtime_v2_runner_spawn_timeout_sec(self) -> float: ...
def get_plugin_runtime_v2_health_check_interval_sec(self) -> float: ...
def get_plugin_runtime_v2_max_restart_attempts(self) -> int: ...
def get_plugin_runtime_v2_scope_approval_file(self) -> str: ...
def get_plugin_runtime_v2_default_rpm(self) -> int: ...
```

**验证**：`grep "get_plugin_runtime_v2_" src/core/protocols.py` 返回 8 行

### T1.2：PluginRuntimeV2Snapshot 快照类型

**文件**：`src/core/types.py`

新增冻结 dataclass：

```python
@dataclass(frozen=True)
class PluginRuntimeV2Snapshot:
    """v2 插件运行时配置快照。"""
    enabled: bool = False
    host_listen_address: str = "0.0.0.0:50051"
    runner_spawn_count: int = 1
    runner_spawn_timeout_sec: float = 30.0
    health_check_interval_sec: float = 60.0
    max_restart_attempts: int = 3
    scope_approval_file: str = "data/scope_approvals.json"
    default_rpm: int = 60
```

在 `protocols.py` 的 TYPE_CHECKING 导入中添加 `PluginRuntimeV2Snapshot`。

**验证**：`from src.core.types import PluginRuntimeV2Snapshot` 不报错

### T1.3：AppConfigPort 适配器实现 8 个方法

**文件**：`src/core/adapters/app_config_port.py`

在 `GlobalConfigAppConfigPort` 中实现 T1.1 的 8 个方法，从 `global_config.plugin_runtime_v2` 读取配置。

**验证**：`grep "get_plugin_runtime_v2_" src/core/adapters/app_config_port.py` 返回 8 行

### T1.4：bot_config.toml 新增 [plugin_runtime_v2] 配置段

**文件**：`src/config/config.py`

1. 在 Pydantic model 中新增 `PluginRuntimeV2Config` 类（字段对应 T1.2 快照）
2. 在 `GlobalConfig` 中新增 `plugin_runtime_v2: PluginRuntimeV2Config = PluginRuntimeV2Config()` 字段
3. 在 `bot_config.toml` 模板中新增 `[plugin_runtime_v2]` 段（所有字段带默认值注释）

**注意**：只改模板+新增版本号，不改动 legacy_migration，不擅自新增 ConfigUpgradeHook（AGENTS.md 规范）

**验证**：`grep "plugin_runtime_v2" src/config/config.py` 返回匹配

---

## T2：重复子目录清理

### T2.1：删除 `src/plugin_runtime_v2/plugin_runtime_v2/`

**操作**：删除整个重复子目录（33 个文件）

**前置验证**：`grep -r "plugin_runtime_v2\.plugin_runtime_v2" src/` 无匹配（已确认 ✅）

**验证**：`ls src/plugin_runtime_v2/plugin_runtime_v2/` 返回不存在

---

## T3：v2 主程序集成

### T3.1：新增 bootstrap.py

**文件**：`src/plugin_runtime_v2/bootstrap.py`（新建）

实现 `init_v2_host_endpoint(app_config_port: AppConfigPort) -> HostEndpoint`：
1. 读取 v2 配置 → 构建 `HostEndpointConfig`
2. 创建 `ScopeApprovalStore` + `TokenService`
3. 创建 `ToolRegistry` + `EventDispatcher` → 构建 `MCPHostBridge`
4. 创建 `PluginRateLimiter`（T5 实现）
5. 创建 `HostEndpoint` → `await endpoint.start()`
6. 返回 endpoint

**验证**：`from src.plugin_runtime_v2.bootstrap import init_v2_host_endpoint` 不报错

### T3.2：main.py 阶段 3 注册 v2 启动组件

**文件**：`src/main.py`

1. `MainSystem.__init__` 新增 `self._v2_host_endpoint: Any | None = None`
2. 在 `_init_components()` 阶段 3 中，在 `plugin_runtime`（order=0）之后注册：

```python
orchestrator.register(StartupComponent(
    name="plugin_runtime_v2", phase=StartupPhase.SUBSYSTEMS, order=1, critical=False,
    init_fn=self._start_plugin_runtime_v2,
))
```

3. 调整现有 `a_memorix` order 从 1→2，`emoji_manager` 从 2→3，`model_config_port_inject` 从 3→4

**验证**：`grep "plugin_runtime_v2" src/main.py` 返回匹配

### T3.3：main.py 新增 _start_plugin_runtime_v2 闭包

**文件**：`src/main.py`

在阶段 3 闭包区域新增：

```python
async def _start_plugin_runtime_v2(self) -> None:
    from src.core.adapters.app_config_port import get_app_config_port
    app_port = get_app_config_port()
    if not app_port.get_plugin_runtime_v2_enabled():
        logger.info("v2 插件运行时未启用，跳过")
        return
    try:
        from src.plugin_runtime_v2.bootstrap import init_v2_host_endpoint
        self._v2_host_endpoint = await init_v2_host_endpoint(app_port)
        await self._inject_scope_services_to_webui()
        logger.info("v2 插件运行时已启动")
    except Exception as e:
        logger.error("v2 插件运行时启动失败: %s", e)
```

**验证**：`grep "_start_plugin_runtime_v2" src/main.py` 返回匹配

### T3.4：main.py 新增 _inject_scope_services_to_webui

**文件**：`src/main.py`

```python
async def _inject_scope_services_to_webui(self) -> None:
    from src.webui.webui_server import get_threaded_webui_server
    webui = get_threaded_webui_server()
    if webui is not None and webui.app is not None:
        webui.app.state.scope_store = self._v2_host_endpoint._scope_store
        webui.app.state.token_service = self._v2_host_endpoint._token_service
```

**验证**：`grep "_inject_scope_services_to_webui" src/main.py` 返回匹配

### T3.5：main.py finally 块新增 v2 关闭

**文件**：`src/main.py`

在 `main()` 的 finally 块中，`await get_plugin_runtime_manager().stop()` 之前新增：

```python
if system._v2_host_endpoint is not None:
    await system._v2_host_endpoint.stop()
```

**验证**：`grep "_v2_host_endpoint" src/main.py` 返回 3+ 处匹配

---

## T4：Scope 审批 WebUI 激活

### T4.1：scope_routes 注册到 WebUI

**文件**：`src/webui/routers/plugin/__init__.py`

新增：

```python
from .scope_routes import router as scope_router
router.include_router(scope_router)
```

**验证**：`grep "scope_routes" src/webui/routers/plugin/__init__.py` 返回匹配

### T4.2：scope_routes None fallback

**文件**：`src/webui/routers/plugin/scope_routes.py`

1. 新增辅助函数：

```python
def _get_scope_store(request: Request) -> ScopeApprovalStore | None:
    return getattr(request.app.state, "scope_store", None)

def _get_token_service(request: Request) -> TokenService | None:
    return getattr(request.app.state, "token_service", None)
```

2. 所有端点中 `request.app.state.scope_store` 改为 `_get_scope_store(request)`，若返回 None 则返回 503

**验证**：`grep "503" src/webui/routers/plugin/scope_routes.py` 返回匹配

---

## T5：Per-Plugin 速率限制

### T5.1：新增 rate_limiter.py

**文件**：`src/plugin_runtime_v2/host/rate_limiter.py`（新建）

实现 `PluginRateLimiter`：
- `__init__(self, default_rpm: int = 60)` — 默认每分钟 60 次
- `check(self, plugin_id: str) -> bool` — 滑动窗口检查，True=允许
- `set_limit(self, plugin_id: str, rpm: int) -> None` — 自定义限制
- `reset(self, plugin_id: str) -> None` — 重置计数器

**验证**：`from src.plugin_runtime_v2.host.rate_limiter import PluginRateLimiter` 不报错

### T5.2：servicer.py 集成 rate_limiter

**文件**：`src/plugin_runtime_v2/host/servicer.py`

1. `_PluginHostServicer.__init__` 新增 `rate_limiter: PluginRateLimiter | None = None` 参数
2. 在 `InvokeTool` RPC 中，调用前检查 `self._rate_limiter.check(plugin_id)`，超限返回 `RESOURCE_EXHAUSTED`

**验证**：`grep "rate_limiter" src/plugin_runtime_v2/host/servicer.py` 返回匹配

### T5.3：HostEndpoint 暴露 scope_store/token_service 属性

**文件**：`src/plugin_runtime_v2/host/endpoint.py`

确认 `_scope_store` 和 `_token_service` 已作为实例属性存储（当前代码 L59-60 已有 `self._scope_store = scope_store` 需确认）。

若不存在，新增属性赋值。同时新增 `@property` 暴露：

```python
@property
def scope_store(self) -> Any:
    return self._scope_store

@property
def token_service(self) -> Any:
    return self._token_service
```

**验证**：`grep "scope_store\|token_service" src/plugin_runtime_v2/host/endpoint.py` 返回 property 定义

---

## T6：Runner 进程管理（最小可行）

### T6.1：新增 runner_spawner.py

**文件**：`src/plugin_runtime_v2/host/runner_spawner.py`（新建）

实现 `RunnerSpawner`：
- `__init__(self, host_listen_address: str, config: RunnerSpawnerConfig)` — RunnerSpawnerConfig 为 dataclass（max_restart_attempts, spawn_timeout_sec）
- `async spawn(self, runner_id: str, plugin_dir: str) -> None` — `subprocess.Popen` 启动 Runner 进程
- `async check_health(self) -> dict[str, str]` — 检查所有进程状态（running/stopped/failed）
- `async restart_failed(self) -> None` — 重启崩溃进程（不超过 max_restart_attempts）
- `async stop_all(self) -> None` — 终止所有进程

**验证**：`from src.plugin_runtime_v2.host.runner_spawner import RunnerSpawner` 不报错

### T6.2：新增 entrypoint.py

**文件**：`src/plugin_runtime_v2/runner/entrypoint.py`（新建）

Runner 独立进程入口，接受 `--host-address`、`--plugin-dir`、`--runner-id` 参数，启动 `RunnerEndpoint`。

**验证**：`python -m src.plugin_runtime_v2.runner.entrypoint --help` 不报错

### T6.3：bootstrap.py 集成 RunnerSpawner

**文件**：`src/plugin_runtime_v2/bootstrap.py`

在 `init_v2_host_endpoint` 中，HostEndpoint 启动后：
1. 创建 `RunnerSpawner`
2. 根据 `runner_spawn_count` 配置 spawn 对应数量的 Runner
3. 将 spawner 挂载到 endpoint 上（新增 `endpoint._runner_spawner` 属性）

**验证**：`grep "RunnerSpawner" src/plugin_runtime_v2/bootstrap.py` 返回匹配

---

## T7：测试

### T7.1：bootstrap 集成测试

**文件**：`tests/plugin_runtime_v2/test_bootstrap.py`（新建）

测试 `init_v2_host_endpoint`：
- v2 未启用时返回 None / 跳过
- v2 启用时创建 HostEndpoint 并成功 start/stop
- 依赖注入链完整（scope_store、token_service、host_bridge 均非 None）

### T7.2：rate_limiter 单元测试

**文件**：`tests/plugin_runtime_v2/test_rate_limiter.py`（新建）

- 默认限制下正常请求通过
- 超限请求被拒绝
- 自定义限制生效
- reset 后计数器清零

### T7.3：runner_spawner 单元测试

**文件**：`tests/plugin_runtime_v2/test_runner_spawner.py`（新建）

- spawn 启动进程
- check_health 返回正确状态
- stop_all 终止所有进程
- 超过 max_restart_attempts 后停止重启

### T7.4：scope_routes 端到端测试

**文件**：`tests/plugin_runtime_v2/test_scope_routes_integration.py`（新建）

- v2 未启用时 GET /plugins/scopes 返回 503
- v2 启用时 GET /plugins/scopes 返回 200

---

## 任务依赖与执行顺序

```
T1 (Protocol+配置) ──→ T3 (主程序集成) ──→ T7 (测试)
     │                      │
     │                      ├─→ T4 (Scope WebUI)
     │                      │
     └─→ T5 (速率限制) ────┘
     
T2 (清理) — 无依赖，随时可做
T6 (Runner管理) — 依赖 T1+T3，与 T4/T5 并行
```

推荐执行顺序：**T1 → T2 → T3 → T4 → T5 → T6 → T7**

## 派发建议

| 任务 | 负责人 | 理由 |
|------|--------|------|
| T1.1~T1.4 | CC | Protocol/适配器/配置层改动，需理解全局架构 |
| T2.1 | Codex | 纯删除操作，机械执行 |
| T3.1~T3.5 | CC | main.py 核心改造，需理解 StartupOrchestrator |
| T4.1~T4.2 | Codex | WebUI 路由注册+fallback，改动小且明确 |
| T5.1~T5.3 | CC | 速率限制设计需与 servicer 集成，需理解 gRPC 调用链 |
| T6.1~T6.3 | Codex | Runner 进程管理，独立模块，接口明确 |
| T7.1~T7.4 | CC | 集成测试需理解完整依赖链 |