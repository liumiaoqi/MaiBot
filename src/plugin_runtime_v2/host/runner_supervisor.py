"""Runner Supervisor — Runner 进程生命周期管理。

整合 spawn + 健康巡检 + 崩溃重启 + 热重载。
RunnerSpawner 保留为底层工具类，Supervisor 在其上增加管理逻辑。
"""

from __future__ import annotations

import asyncio
import signal
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.common.logger import get_logger
from src.plugin_runtime_v2.host.log_forwarder import LogForwarder
from src.plugin_runtime_v2.host.runner_spawner import RunnerSpawner

if TYPE_CHECKING:
    from src.plugin_runtime_v2.host.registry import RunnerRegistry

logger = get_logger("plugin_runtime_v2.host.supervisor")


@dataclass
class RunnerSupervisorConfig:
    """Runner Supervisor 配置。"""

    max_restart_attempts: int = 3
    spawn_timeout_sec: float = 30.0
    restart_initial_delay_s: float = 1.0
    restart_max_delay_s: float = 30.0
    stability_window_s: float = 300.0
    storm_window_s: float = 60.0
    storm_threshold: int = 5
    health_check_interval_s: float = 10.0
    drain_ms: int = 5000


@dataclass
class SpawnResult:
    runner_id: str
    success: bool
    reason: str = ""


@dataclass
class ReloadResult:
    runner_id: str
    success: bool
    reason: str = ""


@dataclass
class RunnerHealthStatus:
    runner_id: str
    status: str = "starting"
    restart_count: int = 0
    last_restart_at: float | None = None
    last_failure_reason: str | None = None
    pid: int | None = None
    uptime_s: float | None = None


class RunnerSupervisor:
    """Runner 进程生命周期管理器。"""

    def __init__(
        self,
        config: RunnerSupervisorConfig,
        registry: RunnerRegistry,
        host_listen_address: str,
        token_service=None,
    ) -> None:
        self._config = config
        self._registry = registry
        self._spawner = RunnerSpawner(host_listen_address=host_listen_address, config=config, token_service=token_service)
        self._log_forwarders: dict[str, LogForwarder] = {}
        self._restart_counts: dict[str, int] = {}
        self._restart_timestamps: dict[str, list[float]] = {}
        self._stable_since: dict[str, float] = {}
        self._reloading: set[str] = set()
        self._health_status: dict[str, RunnerHealthStatus] = {}
        self._started_at: dict[str, float] = {}
        self._shutdown_event: asyncio.Event = asyncio.Event()
        self._health_task: asyncio.Task | None = None

    # ── 生命周期 ──────────────────────────────────────────────

    def start(self) -> None:
        """启动健康巡检 + SIGHUP 注册。"""
        self._health_task = asyncio.create_task(
            self._health_check_loop(), name="supervisor-health",
        )
        if hasattr(signal, "SIGHUP"):
            loop = asyncio.get_event_loop()
            loop.add_signal_handler(
                signal.SIGHUP,
                lambda: asyncio.create_task(self.reload_all()),
            )
        logger.info("RunnerSupervisor 已启动")

    async def stop(self) -> None:
        """停止巡检、清理所有 Runner。"""
        self._shutdown_event.set()
        if self._health_task is not None:
            self._health_task.cancel()
            self._health_task = None
        for lf in self._log_forwarders.values():
            await lf.stop()
        self._log_forwarders.clear()
        await self._spawner.stop_all()
        logger.info("RunnerSupervisor 已停止")

    # ── Spawn ─────────────────────────────────────────────────

    async def spawn(self, runner_id: str, plugin_dir: str) -> SpawnResult:
        """启动 Runner 子进程 + LogForwarder。"""
        proc = await self._spawner.spawn(runner_id, plugin_dir)
        lf = LogForwarder(proc, runner_id)
        await lf.start()
        self._log_forwarders[runner_id] = lf
        self._started_at[runner_id] = time.monotonic()
        self._health_status[runner_id] = RunnerHealthStatus(
            runner_id=runner_id,
            status="starting",
            pid=proc.pid,
        )
        return SpawnResult(runner_id=runner_id, success=True)

    async def spawn_and_wait(
        self, runner_id: str, plugin_dir: str,
    ) -> SpawnResult:
        """Spawn 后轮询 Registry 等待 gRPC 连接。"""
        result = await self.spawn(runner_id, plugin_dir)
        if not result.success:
            return result
        deadline = time.monotonic() + self._config.spawn_timeout_sec
        while time.monotonic() < deadline:
            conn = self._registry.get(runner_id)
            if conn is not None and conn.state.value == "ready":
                self._health_status[runner_id].status = "running"
                return result
            await asyncio.sleep(0.5)
        self._health_status[runner_id].status = "zombie"
        return SpawnResult(runner_id=runner_id, success=False, reason="spawn_timeout")

    # ── 健康巡检 + 崩溃重启 (T4) ──────────────────────────────

    async def check_health(self) -> dict[str, RunnerHealthStatus]:
        """双轨健康检测：进程 poll + registry 连接。"""
        for runner_id, lf in list(self._log_forwarders.items()):
            status = self._health_status.setdefault(
                runner_id,
                RunnerHealthStatus(runner_id=runner_id),
            )
            proc = lf._proc

            if proc.returncode is None:
                conn = self._registry.get(runner_id)
                if conn is not None and conn.state.value == "ready":
                    status.status = "running"
                else:
                    status.status = "zombie"
            elif proc.returncode == 0:
                status.status = "stopped"
            else:
                status.status = "failed"
                status.last_failure_reason = f"exit_code={proc.returncode}"

            if status.status in ("failed", "zombie", "stopped"):
                await self._on_runner_failed(runner_id, status.status)
        return self._health_status

    async def _health_check_loop(self) -> None:
        """定时巡检。"""
        try:
            while not self._shutdown_event.is_set():
                await asyncio.sleep(self._config.health_check_interval_s)
                if self._shutdown_event.is_set():
                    return
                await self.check_health()
                self._reset_counters_if_stable()
        except asyncio.CancelledError:
            pass

    async def _on_runner_failed(self, runner_id: str, reason: str) -> None:
        """Runner 失败 → 判断是否重启。"""
        if runner_id in self._reloading:
            return
        if not self._should_restart(runner_id):
            return
        count = self._restart_counts.get(runner_id, 0)
        delay = min(
            self._config.restart_initial_delay_s * (2 ** count),
            self._config.restart_max_delay_s,
        )
        logger.warning(
            "Runner %s 异常 (%s)，%.1fs 后重启 (%d/%d)",
            runner_id, reason, delay, count + 1, self._config.max_restart_attempts,
        )
        await asyncio.sleep(delay)

        # 停止旧进程 + 注销
        lf = self._log_forwarders.pop(runner_id, None)
        if lf is not None:
            await lf.stop()
        self._registry.unregister(runner_id)

        # 记录重启
        self._restart_counts[runner_id] = count + 1
        ts = self._restart_timestamps.setdefault(runner_id, [])
        ts.append(time.monotonic())
        self._health_status[runner_id].restart_count = count + 1
        self._health_status[runner_id].last_restart_at = time.monotonic()
        self._health_status[runner_id].last_failure_reason = reason

        # 重启（需要 plugin_dir 信息 — 从 Spawner 的 proc 记录中获取）
        await self._spawner.restart_failed()

    def _should_restart(self, runner_id: str) -> bool:
        """检查是否应该重启（计数器 + 风暴检测）。"""
        count = self._restart_counts.get(runner_id, 0)
        if count >= self._config.max_restart_attempts:
            return False
        timestamps = self._restart_timestamps.get(runner_id, [])
        if timestamps:
            recent = [t for t in timestamps if time.monotonic() - t < self._config.storm_window_s]
            if len(recent) >= self._config.storm_threshold:
                logger.error(
                    "Runner %s 触发风暴检测: %d 次重启/%ds",
                    runner_id, len(recent), self._config.storm_window_s,
                )
                return False
        return True

    def _reset_counters_if_stable(self) -> None:
        """恢复计数器：稳定运行超过 stability_window_s 时重置。"""
        for runner_id, since in list(self._stable_since.items()):
            if time.monotonic() - since > self._config.stability_window_s:
                if self._restart_counts.get(runner_id, 0) > 0:
                    logger.info("Runner %s 稳定运行，重置重启计数器", runner_id)
                self._restart_counts.pop(runner_id, None)
                self._restart_timestamps.pop(runner_id, None)

    # ── 心跳回调 (T5) ────────────────────────────────────────

    async def _on_heartbeat_timeout(self, runner_id: str) -> None:
        """心跳超时 → 触发重启流程。"""
        await self._on_runner_failed(runner_id, "heartbeat_timeout")

    # ── 热重载 (T5) ───────────────────────────────────────────

    async def reload_all(self, drain_ms: int = 0) -> dict[str, ReloadResult]:
        """重载所有 Runner。"""
        if drain_ms == 0:
            drain_ms = self._config.drain_ms
        results: dict[str, ReloadResult] = {}
        for runner_id in list(self._log_forwarders.keys()):
            results[runner_id] = await self.reload_one(runner_id, drain_ms)
        return results

    async def reload_one(self, runner_id: str, drain_ms: int = 0) -> ReloadResult:
        """重载单个 Runner：关停 → 等待排空 → 重启。"""
        if drain_ms == 0:
            drain_ms = self._config.drain_ms
        if runner_id in self._reloading:
            return ReloadResult(runner_id=runner_id, success=False, reason="already_reloading")
        conn = self._registry.get(runner_id)
        if conn is None or conn.state.value != "ready":
            return ReloadResult(runner_id=runner_id, success=False, reason="not_ready")

        self._reloading.add(runner_id)
        try:
            # 停止旧进程
            lf = self._log_forwarders.pop(runner_id, None)
            if lf is not None:
                await lf.stop()
            self._registry.unregister(runner_id)

            # 等待排空 + 重启
            await asyncio.sleep(drain_ms / 1000.0)
            await self._spawner.restart_failed()
            return ReloadResult(runner_id=runner_id, success=True)
        except Exception as exc:
            logger.warning("操作异常 in runner_supervisor.py", exc_info=True)
            return ReloadResult(runner_id=runner_id, success=False, reason=str(exc))
        finally:
            self._reloading.discard(runner_id)

    # ── 状态查询 ─────────────────────────────────────────────

    def get_health_status(self) -> dict[str, RunnerHealthStatus]:
        return dict(self._health_status)
