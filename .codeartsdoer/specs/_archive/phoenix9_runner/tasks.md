# Phoenix-9：Runner 进程管理增强 — 编码任务

## 前置条件

- spec.md: `.codeartsdoer/specs/phoenix9_runner/spec.md`
- design.md: `.codeartsdoer/specs/phoenix9_runner/design.md`
- 依赖：Phoenix-8（V1 兼容层）已完成

## 任务列表

### T1: LogForwarder — Runner stdout/stderr 消费

**目标**：异步读取 Runner 子进程的 stdout/stderr，转发到 Host 日志系统。

**文件**：`src/plugin_runtime_v2/host/log_forwarder.py`（新建）

**内容**：
- `LogForwarder` 类，接收 `subprocess.Popen` 实例和 `runner_id`
- 两个 `asyncio.Task` 分别读取 stdout 和 stderr
- 每行通过 `logger.info("[runner:%s] %s", runner_id, line)` 转发
- `start()` / `stop()` 生命周期方法
- 处理 `BrokenPipeError` 和 `ValueError`（流已关闭）

**验收**：Runner 子进程的 print/logging 输出出现在 Host 日志中。

---

### T2: RunnerSupervisorConfig + RunnerHealthStatus 数据模型

**目标**：定义 Supervisor 配置和健康状态数据类。

**文件**：`src/plugin_runtime_v2/host/runner_supervisor.py`（新建，先只放数据模型）

**内容**：
- `RunnerSupervisorConfig` dataclass（9 个字段，见 design.md 1.3.3）
- `RunnerHealthStatus` dataclass（7 个字段，见 design.md 1.3.2）
- `SpawnResult` / `ReloadResult` dataclass
- 所有字段带默认值，取值范围在 docstring 中标注

**验收**：可导入，默认值合理。

---

### T3: RunnerSupervisor 核心生命周期 + Spawn

**目标**：实现 Supervisor 的 start/stop/spawn/spawn_and_wait。

**文件**：`src/plugin_runtime_v2/host/runner_supervisor.py`

**内容**：
- `RunnerSupervisor.__init__`：创建 RunnerSpawner、LogForwarder 字典、状态字典
- `start()`：启动健康巡检定时任务 + SIGHUP 注册
- `stop()`：取消巡检任务 + stop_all Runner + 清理 LogForwarder
- `spawn()`：调用 Spawner.spawn + 启动 LogForwarder
- `spawn_and_wait()`：spawn 后等待 gRPC 连接出现（轮询 RunnerRegistry，超时返回 FAILED）
- SIGHUP 条件注册（`signal.SIGUP` 仅 Unix）

**验收**：spawn 后 Runner 子进程 stdout/stderr 出现在 Host 日志；spawn_and_wait 超时返回 FAILED。

---

### T4: 健康巡检 + 崩溃重启

**目标**：实现定时巡检循环、崩溃检测、自动重启、计数器重置、风暴检测。

**文件**：`src/plugin_runtime_v2/host/runner_supervisor.py`

**内容**：
- `_health_check_loop()`：每隔 `health_check_interval_s` 执行一次
- `check_health()`：双轨检测（进程 poll + gRPC registry），返回 RunnerHealthStatus
- `_on_runner_failed()`：检测到崩溃后的处理入口
- `_should_restart()`：检查计数器 + 风暴检测
- `_reset_counter_if_stable()`：稳定运行 `stability_window_s` 后重置
- `_on_heartbeat_timeout()`：心跳超时回调，触发 `_on_runner_failed`
- 指数退避延迟：`min(initial * 2^attempt, max_delay)`

**验收**：Runner 崩溃后自动重启；重启 3 次后停止；稳定 5 分钟后计数器重置；60s 内 5 次重启触发风暴检测。

---

### T5: 热重载

**目标**：实现渐进式热重载（rolling reload）。

**文件**：`src/plugin_runtime_v2/host/runner_supervisor.py`

**内容**：
- `reload_all()`：逐个调用 `reload_one()`，返回结果字典
- `reload_one()`：检查状态 → 发送 ShutdownRequest(drain_ms) → 等待排空 → kill → spawn → 等待重连
- 防重入：`_reloading` set 记录正在重载的 Runner
- 跳过非 READY 状态的 Runner
- 排空期间 Runner 崩溃：跳过等待，直接 spawn

**验收**：reload_all 逐个重载，每时刻 N-1 个可用；非 READY Runner 被跳过。

---

### T6: HostEndpoint 正式注入 + bootstrap 集成

**目标**：将 RunnerSupervisor 正式集成到 HostEndpoint 和 bootstrap 流程。

**文件**：
- `src/plugin_runtime_v2/host/endpoint.py`（修改）
- `src/plugin_runtime_v2/bootstrap.py`（修改）
- `src/plugin_runtime_v2/host/servicer.py`（修改）

**内容**：
- `HostEndpoint.set_supervisor(supervisor)` 正式 setter
- `HostEndpoint.stop()` 中通过 `self._supervisor` 调用 stop（替代 `getattr(self, "_runner_spawner")`）
- `HostEndpoint.get_status()` 扩展，包含 Supervisor 的健康状态
- `HostEndpoint.reload_runners()` 公开方法，供 WebUI API 调用
- `bootstrap.py`：用 `RunnerSupervisor` 替代 `RunnerSpawner`，调用 `set_supervisor()`
- `servicer.py`：心跳超时回调中通知 Supervisor

**验收**：HostEndpoint 启动后 Supervisor 自动开始巡检；心跳超时触发 Supervisor 重启；WebUI 可通过 API 触发热重载。

---

### T7: 单元测试

**目标**：覆盖 Supervisor 核心逻辑的单元测试。

**文件**：`tests/plugin_runtime_v2/test_runner_supervisor.py`（新建）

**内容**：
- RunnerSupervisorConfig 默认值测试
- RunnerHealthStatus 构造测试
- 健康检查逻辑测试（mock subprocess + registry）
- 重启计数器 + 风暴检测测试
- 计数器重置测试（mock time.monotonic）
- 热重载逻辑测试（mock HostEndpoint + Spawner）
- LogForwarder 测试（mock subprocess.PIPE）

**验收**：所有测试通过。

---

### T8: 集成验证

**目标**：Docker 内验证 Supervisor 完整生命周期。

**内容**：
- 启动 HostEndpoint + Supervisor
- spawn Runner 并验证 gRPC 连接建立
- kill Runner 子进程，验证自动重启
- 触发热重载，验证渐进式重载
- 验证 stdout/stderr 日志转发

**验收**：Docker 内完整生命周期验证通过。