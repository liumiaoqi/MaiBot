"""Runner Supervisor — 数据模型。

Defines RunnerSupervisorConfig and result/health status types.
Supervisor logic (spawn/monitor/restart) implemented in T3 by CC.
"""

from __future__ import annotations

from dataclasses import dataclass


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
    """spawn 操作结果。"""

    runner_id: str
    success: bool
    reason: str = ""


@dataclass
class ReloadResult:
    """热重载操作结果。"""

    runner_id: str
    success: bool
    reason: str = ""


@dataclass
class RunnerHealthStatus:
    """Runner 健康状态快照。"""

    runner_id: str
    status: str = "starting"
    restart_count: int = 0
    last_restart_at: float | None = None
    last_failure_reason: str | None = None
    pid: int | None = None
    uptime_s: float | None = None
