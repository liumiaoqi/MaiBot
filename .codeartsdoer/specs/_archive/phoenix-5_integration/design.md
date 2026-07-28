# Phoenix-5：v2 主程序集成 — 技术设计

# **1. 设计目标**

将 plugin_runtime_v2 的 gRPC HostEndpoint 接入 main.py 的 StartupOrchestrator，实现 v2 启动/停止生命周期，激活 Scope 审批 WebUI，清理重复子目录，增加 per-plugin 速率限制。

# **2. 整体架构**

## **2.1 启动编排**

main.py 使用 `StartupOrchestrator` 6 阶段编排（`src/core/startup.py`）。v2 初始化插入阶段 3（SUBSYSTEMS），与 v1 并行：

```
阶段 0: CONFIG_LOAD
阶段 1: INFRASTRUCTURE
阶段 2: CORE_SERVICES（Protocol 注册）
阶段 3: SUBSYSTEMS
  ├─ plugin_runtime (v1, order=0, critical=False)
  ├─ plugin_runtime_v2 (新增, order=1, critical=False)  ← 新增
  ├─ a_memorix (order=2, critical=False)
  ├─ emoji_manager (order=3, critical=False)
  └─ model_config_port_inject (order=4, critical=False)
阶段 4: SESSION_RESTORE
阶段 5: READY
```

v2 设为 `critical=False`——启动失败不影响主程序。

## **2.2 关闭编排**

main.py 的 `main()` finally 块中新增 v2 关闭：

```python
finally:
    # ... 现有关闭逻辑 ...
    await _stop_plugin_runtime_v2()  # 新增
    await async_task_manager.stop_and_wait_all_tasks()
```

## **2.3 依赖注入链**

```
main.py
  → _init_plugin_runtime_v2()
    → 创建 ScopeApprovalStore + TokenService
    → 创建 ToolRegistry + EventDispatcher
    → 创建 MCPHostBridge(tool_registry, event_dispatcher, person_info_port)
    → 创建 HostEndpoint(config, host_bridge, token_service, scope_store)
    → await host_endpoint.start()
    → 注入 scope_store/token_service 到 WebUI app.state
```

# **3. v2 主程序集成**

## **3.1 main.py 改造**

### **3.1.1 新增启动组件**

在 `_init_components()` 的阶段 3 中新增：

```python
orchestrator.register(StartupComponent(
    name="plugin_runtime_v2", phase=StartupPhase.SUBSYSTEMS, order=1, critical=False,
    init_fn=self._start_plugin_runtime_v2,
))
```

### **3.1.2 新增初始化函数**

```python
async def _start_plugin_runtime_v2(self) -> None:
    from src.core.adapters.app_config_port import get_app_config_port
    app_port = get_app_config_port()
    if not app_port.get_plugin_runtime_v2_enabled():
        logger.info("v2 插件运行时未启用，跳过")
        return
    try:
        self._v2_host_endpoint = await _init_v2_host_endpoint(app_port)
        await _inject_scope_services_to_webui(self._v2_host_endpoint)
        logger.info("v2 插件运行时已启动")
    except Exception as e:
        logger.error("v2 插件运行时启动失败: %s", e)
```

### **3.1.3 新增关闭逻辑**

在 `main()` 的 finally 块中：

```python
if system._v2_host_endpoint is not None:
    await system._v2_host_endpoint.stop()
```

### **3.1.4 MainSystem 新增属性**

```python
class MainSystem:
    def __init__(self) -> None:
        # ... 现有属性 ...
        self._v2_host_endpoint: Any | None = None
```

## **3.2 HostEndpoint 初始化函数**

新增模块 `src/plugin_runtime_v2/bootstrap.py`，集中 v2 初始化逻辑：

```python
async def init_v2_host_endpoint(app_config_port: AppConfigPort) -> HostEndpoint:
    """创建并启动 v2 HostEndpoint，组装所有依赖。"""
    
    # 1. 配置
    config = HostEndpointConfig(
        listen_address=app_config_port.get_plugin_runtime_v2_host_listen_address(),
        heartbeat_interval_s=app_config_port.get_plugin_runtime_v2_health_check_interval_sec(),
    )
    
    # 2. Scope 服务
    scope_store = ScopeApprovalStore(
        file_path=app_config_port.get_plugin_runtime_v2_scope_approval_file(),
    )
    token_service = TokenService()
    
    # 3. MCP 桥接
    tool_registry = ToolRegistry()
    event_dispatcher = EventDispatcher()
    person_info_port = get_person_info_port()
    host_bridge = MCPHostBridge(tool_registry, event_dispatcher, person_info_port)
    
    # 4. 速率限制
    rate_limiter = PluginRateLimiter(
        default_rpm=app_config_port.get_plugin_runtime_v2_default_rpm(),
    )
    
    # 5. 创建并启动 HostEndpoint
    endpoint = HostEndpoint(
        config=config,
        host_bridge=host_bridge,
        token_service=token_service,
        scope_store=scope_store,
    )
    await endpoint.start()
    
    return endpoint
```

## **3.3 v1/v2 隔离**

- v1 和 v2 使用不同的端口（v1: IPC UDS/TCP，v2: gRPC 50051）
- v1 的 `PluginRuntimeManager` 和 v2 的 `HostEndpoint` 完全独立
- v2 启动失败时 v1 不受影响（`critical=False`）

# **4. Scope 审批 WebUI 激活**

## **4.1 scope_routes 注册**

**文件**：`src/webui/routers/plugin/__init__.py`

```python
from .scope_routes import router as scope_router
router.include_router(scope_router)
```

## **4.2 scope_store/token_service 注入**

**问题**：scope_routes.py 通过 `request.app.state.scope_store` / `request.app.state.token_service` 获取实例，但 WebUI 应用启动时未创建和注入。

**方案**：在 `_start_plugin_runtime_v2()` 中，创建 HostEndpoint 后，将 scope_store 和 token_service 注入到 WebUI 的 app.state：

```python
async def _inject_scope_services_to_webui(self, host_endpoint: HostEndpoint) -> None:
    from src.webui.webui_server import get_threaded_webui_server
    webui = get_threaded_webui_server()
    if webui is not None and webui.app is not None:
        webui.app.state.scope_store = host_endpoint._scope_store
        webui.app.state.token_service = host_endpoint._token_service
```

**注意**：WebUI 运行在独立线程中，`app.state` 赋值是线程安全的（FastAPI 的 `State` 内部是简单属性赋值）。

## **4.3 scope_routes 的 scope_store 获取方式**

当前 scope_routes.py 假设 `request.app.state.scope_store` 已存在。如果 v2 未启用，该属性不存在。需增加 fallback：

```python
def _get_scope_store(request: Request) -> ScopeApprovalStore | None:
    return getattr(request.app.state, "scope_store", None)
```

如果 scope_store 为 None，API 返回 503 Service Unavailable。

# **5. 重复子目录清理**

## **5.1 删除 `src/plugin_runtime_v2/plugin_runtime_v2/`**

31 个 .py 文件的完整拷贝。删除前确认无外部引用。

## **5.2 验证**

```bash
grep -r "plugin_runtime_v2.plugin_runtime_v2" src/
# 应无匹配
```

# **6. Runner 进程管理**

## **6.1 当前状态**

v2 的 RunnerEndpoint 假设 Runner 进程已独立启动。v1 的 PluginSupervisor 有完整的 spawn/健康检查/自动重启机制。

## **6.2 设计决策**

Phoenix-5 实现最小可行的 Runner 进程管理——Host 端 spawn Runner 子进程。完整的进程管理增强留给 Phoenix-9。

### **6.2.1 RunnerSpawner**

新增 `src/plugin_runtime_v2/host/runner_spawner.py`：

```python
class RunnerSpawner:
    """Host 端 Runner 子进程管理器。"""
    
    def __init__(self, host_listen_address: str, plugin_dirs: list[str], config: RunnerSpawnerConfig) -> None:
        self._host_addr = host_listen_address
        self._plugin_dirs = plugin_dirs
        self._config = config
        self._processes: dict[str, subprocess.Popen] = {}  # runner_id → process
        self._restart_counts: dict[str, int] = {}
    
    async def spawn(self, runner_id: str, plugin_dir: str) -> None:
        """spawn 一个 Runner 子进程。"""
        cmd = [
            sys.executable, "-m", "src.plugin_runtime_v2.runner.entrypoint",
            "--host-address", self._host_addr,
            "--plugin-dir", plugin_dir,
            "--runner-id", runner_id,
        ]
        process = subprocess.Popen(cmd, ...)
        self._processes[runner_id] = process
    
    async def check_health(self) -> dict[str, str]:
        """检查所有 Runner 进程健康状态。"""
        ...
    
    async def restart_failed(self) -> None:
        """重启崩溃的 Runner 进程（不超过 max_restart_attempts）。"""
        ...
    
    async def stop_all(self) -> None:
        """停止所有 Runner 进程。"""
        ...
```

### **6.2.2 Runner 入口脚本**

新增 `src/plugin_runtime_v2/runner/entrypoint.py`：

```python
"""Runner 独立进程入口 — 由 Host 的 RunnerSpawner 调用。"""
import argparse
import asyncio

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host-address", required=True)
    parser.add_argument("--plugin-dir", required=True)
    parser.add_argument("--runner-id", required=True)
    args = parser.parse_args()
    
    asyncio.run(_run(args))

async def _run(args):
    from src.plugin_runtime_v2.runner.endpoint import RunnerEndpoint
    endpoint = RunnerEndpoint(...)
    await endpoint.start()

if __name__ == "__main__":
    main()
```

### **6.2.3 配置驱动**

Runner spawn 数量、超时、重启策略通过 AppConfigPort 配置（见 spec.md 6.1 节）。

# **7. Per-Plugin 速率限制**

## **7.1 设计**

新增 `src/plugin_runtime_v2/host/rate_limiter.py`：

```python
class PluginRateLimiter:
    """Per-plugin 速率限制器 — 防止插件滥用 scope。"""
    
    def __init__(self, default_rpm: int = 60) -> None:
        self._default_rpm = default_rpm
        self._limits: dict[str, int] = {}  # plugin_id → rpm
        self._counters: dict[str, list[float]] = {}  # plugin_id → timestamps
    
    def check(self, plugin_id: str) -> bool:
        """检查插件是否超过速率限制。返回 True 表示允许。"""
        ...
    
    def set_limit(self, plugin_id: str, rpm: int) -> None:
        """为特定插件设置自定义速率限制。"""
        ...
```

## **7.2 集成点**

速率限制在 `_PluginHostServicer` 的 `Connect` 方法和 `InvokeTool` RPC 中检查：

- Connect 握手时不限制（一次性操作）
- InvokeTool 时检查 `rate_limiter.check(plugin_id)`，超限返回 `RESOURCE_EXHAUSTED`

## **7.3 配置**

AppConfigPort 新增 `get_plugin_runtime_v2_default_rpm() -> int`（默认 60 次/分钟）。

# **8. 新增 AppConfigPort 方法**

| 方法 | 签名 | 默认值 |
|------|------|--------|
| `get_plugin_runtime_v2_enabled` | `-> bool` | `False` |
| `get_plugin_runtime_v2_host_listen_address` | `-> str` | `"0.0.0.0:50051"` |
| `get_plugin_runtime_v2_runner_spawn_count` | `-> int` | `1` |
| `get_plugin_runtime_v2_runner_spawn_timeout_sec` | `-> float` | `30.0` |
| `get_plugin_runtime_v2_health_check_interval_sec` | `-> float` | `60.0` |
| `get_plugin_runtime_v2_max_restart_attempts` | `-> int` | `3` |
| `get_plugin_runtime_v2_scope_approval_file` | `-> str` | `"data/scope_approvals.json"` |
| `get_plugin_runtime_v2_default_rpm` | `-> int` | `60` |

# **9. 新增文件清单**

| 文件 | 职责 |
|------|------|
| `src/plugin_runtime_v2/bootstrap.py` | v2 初始化入口，组装 HostEndpoint 依赖 |
| `src/plugin_runtime_v2/host/runner_spawner.py` | Runner 子进程管理器 |
| `src/plugin_runtime_v2/host/rate_limiter.py` | Per-plugin 速率限制器 |
| `src/plugin_runtime_v2/runner/entrypoint.py` | Runner 独立进程入口 |

# **10. 修改文件清单**

| 文件 | 改动 |
|------|------|
| `src/main.py` | +阶段3 v2 启动组件，+finally 关闭逻辑，+_v2_host_endpoint 属性 |
| `src/webui/routers/plugin/__init__.py` | +scope_routes include |
| `src/webui/routers/plugin/scope_routes.py` | +scope_store None fallback |
| `src/core/protocols.py` | +AppConfigPort 8 个新方法 |
| `src/core/types.py` | +PluginRuntimeV2Snapshot |
| `src/core/adapters/app_config_port.py` | +8 个新方法实现 |
| `src/config/config.py` | +plugin_runtime_v2 配置段 |
| `src/plugin_runtime_v2/host/endpoint.py` | +scope_store/token_service 属性暴露 |
| `src/plugin_runtime_v2/host/servicer.py` | +rate_limiter 集成 |

# **11. 风险与缓解**

| 风险 | 缓解 |
|------|------|
| v2 启动失败影响主程序 | `critical=False` + try/except 包裹 |
| WebUI app.state 线程安全 | FastAPI State 是简单属性赋值，线程安全 |
| Runner 子进程僵尸进程 | RunnerSpawner 定期 check_health + stop_all |
| gRPC 端口冲突 | HostEndpointConfig 使用 `0.0.0.0:0` 自动分配端口 |
| scope_routes 在 v2 未启用时崩溃 | None fallback + 503 响应 |