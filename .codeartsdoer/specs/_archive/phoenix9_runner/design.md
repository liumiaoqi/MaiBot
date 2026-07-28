# Phoenix-9：Runner 进程管理增强 — 技术设计

# 1. 实现模型

## 1.1 上下文视图

核心改造：将 `RunnerSpawner` 升级为 `RunnerSupervisor`，整合 spawn + 健康巡检 + 崩溃重启 + 热重载。`RunnerSpawner` 保留为纯 spawn/stop 的底层工具类，`RunnerSupervisor` 在其上增加生命周期管理逻辑。

```
                    ┌─────────────┐
  SIGHUP ──────────►│             │
                    │  Runner     │
  WebUI ───────────►│  Supervisor │──► subprocess.Popen (spawn)
                    │             │──► proc.kill/terminate (stop)
  HeartbeatManager ─►│             │──► RunnerRegistry (查询连接)
  (on_timeout)      │             │──► HostEndpoint (request_shutdown)
                    └─────────────┘
                           │
                    ┌──────┴──────┐
                    │  Runner     │
                    │  Spawner    │ (纯 spawn/stop，无巡检)
                    └─────────────┘
```

## 1.2 服务/组件总体架构

### 新增组件

| 组件 | 文件 | 职责 |
|------|------|------|
| `RunnerSupervisor` | `host/runner_supervisor.py` | 生命周期管理（巡检+重启+重载） |
| `LogForwarder` | `host/log_forwarder.py` | Runner stdout/stderr 异步消费+转发 |

### 修改组件

| 组件 | 文件 | 变更 |
|------|------|------|
| `RunnerSpawner` | `host/runner_spawner.py` | 新增 `spawn_sync` + `wait_for_exit`，保留为纯工具类 |
| `HostEndpoint` | `host/endpoint.py` | 新增 `set_supervisor()` 正式注入接口，移除 `_runner_spawner` 私有属性 |
| `bootstrap.py` | `bootstrap.py` | 用 `RunnerSupervisor` 替代 `RunnerSpawner`，注入到 HostEndpoint |
| `HeartbeatManager` | `host/heartbeat.py` | 新增 `on_timeout` 回调注册，供 Supervisor 订阅心跳超时事件 |

### 复用组件（不修改）

| 组件 | 文件 | 复用方式 |
|------|------|---------|
| `RunnerRegistry` | `host/registry.py` | Supervisor 查询 gRPC 连接状态 |
| `ReconnectPolicy` | `runner/reconnect.py` | Runner 端重连策略不变 |
| `HostEndpointConfig` | `host/connection.py` | 新增 `drain_ms` 配置项 |

## 1.3 实现设计文档

### 1.3.1 RunnerSupervisor

```python
class RunnerSupervisor:
    """Runner 生命周期管理器 — 巡检+重启+重载。"""

    def __init__(
        self,
        host_listen_address: str,
        registry: RunnerRegistry,
        config: RunnerSupervisorConfig,
    ) -> None:
        self._spawner = RunnerSpawner(host_listen_address, config)
        self._registry = registry
        self._config = config
        self._log_forwarders: dict[str, LogForwarder] = {}
        self._restart_counts: dict[str, int] = {}
        self._restart_timestamps: dict[str, list[float]] = {}  # 风暴检测
        self._stable_since: dict[str, float] = {}  # 计数器重置
        self._health_task: asyncio.Task | None = None
        self._reloading: set[str] = set()  # 正在重载的 Runner（防重入）
        self._shutdown_event = asyncio.Event()

    # ── 生命周期 ──
    async def start(self) -> None: ...
    async def stop(self) -> None: ...

    # ── Spawn ──
    async def spawn(self, runner_id: str, plugin_dir: str) -> SpawnResult: ...
    async def spawn_and_wait(self, runner_id: str, plugin_dir: str) -> SpawnResult: ...

    # ── 健康巡检 ──
    async def _health_check_loop(self) -> None: ...
    async def check_health(self) -> dict[str, RunnerHealthStatus]: ...

    # ── 崩溃重启 ──
    async def _on_runner_failed(self, runner_id: str, reason: str) -> None: ...
    async def _on_heartbeat_timeout(self, runner_id: str) -> None: ...
    def _should_restart(self, runner_id: str) -> bool: ...  # 计数器+风暴检测
    def _reset_counter_if_stable(self, runner_id: str) -> None: ...

    # ── 热重载 ──
    async def reload_all(self, drain_ms: int = 5000) -> dict[str, ReloadResult]: ...
    async def reload_one(self, runner_id: str, drain_ms: int = 5000) -> ReloadResult: ...

    # ── 状态查询 ──
    def get_status(self) -> dict[str, RunnerHealthStatus]: ...
```

### 1.3.2 RunnerHealthStatus

```python
@dataclass
class RunnerHealthStatus:
    runner_id: str
    status: str  # "running" | "stopped" | "failed" | "zombie" | "starting"
    restart_count: int
    last_restart_at: float | None
    last_failure_reason: str | None
    pid: int | None
    uptime_s: float | None
```

### 1.3.3 RunnerSupervisorConfig

```python
@dataclass
class RunnerSupervisorConfig:
    max_restart_attempts: int = 3
    spawn_timeout_sec: float = 30.0
    restart_initial_delay_s: float = 1.0
    restart_max_delay_s: float = 30.0
    stability_window_s: float = 300.0
    storm_window_s: float = 60.0
    storm_threshold: int = 5
    health_check_interval_s: float = 10.0
    drain_ms: int = 5000
```

### 1.3.4 LogForwarder

```python
class LogForwarder:
    """异步读取子进程 stdout/stderr 并转发到 Host 日志。"""

    def __init__(self, process: subprocess.Popen, runner_id: str) -> None: ...
    async def start(self) -> None: ...  # 启动两个 asyncio.Task 读取
    async def stop(self) -> None: ...   # 取消读取任务
```

### 1.3.5 HeartbeatManager 扩展

不修改 HeartbeatManager 内部逻辑，而是在 Servicer 层将心跳超时回调桥接到 Supervisor：

```python
# servicer.py 中已有的 timeout_callback
async def _on_heartbeat_timeout(rid: str) -> None:
    logger.warning("Runner %s 心跳超时，关闭双向流", rid)
    await context.abort(grpc.StatusCode.UNAVAILABLE, "heartbeat timeout")
    # 新增：通知 Supervisor
    if self._supervisor is not None:
        await self._supervisor._on_heartbeat_timeout(rid)
```

# 2. 接口设计

## 2.1 总体设计

Supervisor 对外暴露 3 类接口：
1. **生命周期**：`start()` / `stop()` — 由 bootstrap.py 调用
2. **运维操作**：`reload_all()` / `reload_one()` — 由 WebUI 或 SIGHUP 触发
3. **状态查询**：`get_status()` / `check_health()` — 由 WebUI 调用

## 2.2 接口清单

| 接口 | 签名 | 调用方 | 说明 |
|------|------|--------|------|
| `spawn` | `async spawn(runner_id, plugin_dir) -> SpawnResult` | bootstrap | spawn 后不等待 gRPC 连接 |
| `spawn_and_wait` | `async spawn_and_wait(runner_id, plugin_dir) -> SpawnResult` | bootstrap | spawn 后等待 gRPC 连接就绪 |
| `reload_all` | `async reload_all(drain_ms) -> dict[str, ReloadResult]` | WebUI/SIGHUP | 渐进式重载所有 Runner |
| `reload_one` | `async reload_one(runner_id, drain_ms) -> ReloadResult` | WebUI | 重载单个 Runner |
| `get_status` | `get_status() -> dict[str, RunnerHealthStatus]` | WebUI | 获取所有 Runner 健康状态 |
| `check_health` | `async check_health() -> dict[str, RunnerHealthStatus]` | 内部 | 执行一次健康检查 |
| `_on_heartbeat_timeout` | `async _on_heartbeat_timeout(runner_id) -> None` | Servicer | 心跳超时回调 |
| `set_supervisor` | `HostEndpoint.set_supervisor(supervisor)` | bootstrap | 正式注入接口 |

# 3. 关键设计决策

## 3.1 RunnerSpawner vs RunnerSupervisor 分层

**决策**：保留 RunnerSpawner 为纯 spawn/stop 工具类，RunnerSupervisor 在其上增加巡检+重启+重载逻辑。

**理由**：
- 单一职责：Spawner 只管进程创建/销毁，Supervisor 管生命周期策略
- CompatBridge（Phoenix-8）已复用 RunnerSpawner 的 spawn 模式，分层后不影响
- 测试友好：Spawner 可独立测试，Supervisor 可 mock Spawner

## 3.2 健康巡检定时任务 vs 事件驱动

**决策**：双轨制 — 进程级用定时巡检，gRPC 级用心跳超时事件驱动。

**理由**：
- 进程崩溃（SIGSEGV 等）不会产生事件，只能靠 poll() 检测
- gRPC 连接丢失有心跳机制，事件驱动更实时
- 两者互补：巡检捕获进程级崩溃，心跳捕获网络级断开

## 3.3 重启计数器重置策略

**决策**：Runner 稳定运行 `stability_window_s`（默认 300s）后重置计数器。

**理由**：
- 永久不重置会导致偶发崩溃后永久放弃（如 OOM 后恢复）
- 窗口太短会导致重启风暴无法被检测
- 5 分钟是合理的稳定判定窗口

## 3.4 热重载：渐进式 vs 全量

**决策**：渐进式（rolling reload），逐个重载。

**理由**：
- 全量重载会导致服务中断（所有 Runner 同时不可用）
- 渐进式保证每时刻 N-1 个 Runner 可用
- 实现简单：for loop + await，无需并发控制

## 3.5 SIGHUP 处理

**决策**：在 Supervisor.start() 中注册 signal.SIGHUP 处理器，调用 reload_all()。SIGHUP 只由 Host 主进程捕获，通过 gRPC ShutdownRequest 通知 Runner 排空重启，Runner 端无需注册 SIGHUP handler。

**理由**：
- SIGHUP 是 Unix 传统的重载信号
- Docker 环境中 `docker kill -s HUP <container>` 可触发
- Windows 不支持 SIGHUP，需条件注册
- Runner 是 subprocess.Popen 启动的子进程，默认 SIGHUP 行为是终止，因此必须由 Host 捕获后通过 gRPC 协议通知 Runner 优雅排空，而非依赖信号传递

# 4. 数据模型

## 4.1 设计目标

- RunnerHealthStatus 是只读快照，供 WebUI 展示
- RestartTimestamps 用于风暴检测的时间窗口计算
- SpawnResult/ReloadResult 是操作结果，包含成功/失败/原因

## 4.2 模型实现

```python
@dataclass
class SpawnResult:
    runner_id: str
    success: bool
    reason: str = ""  # "ok" | "timeout" | "spawn_error"

@dataclass
class ReloadResult:
    runner_id: str
    success: bool
    reason: str = ""  # "ok" | "drain_timeout" | "spawn_failed" | "skipped_not_ready"

@dataclass
class RunnerHealthStatus:
    runner_id: str
    status: str  # "running" | "stopped" | "failed" | "zombie" | "starting"
    restart_count: int
    last_restart_at: float | None  # monotonic time
    last_failure_reason: str | None
    pid: int | None
    uptime_s: float | None
```