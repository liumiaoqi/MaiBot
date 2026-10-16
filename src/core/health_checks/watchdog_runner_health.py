"""watchdog.runner_health 健康检查 — Runner 健康状态。

通过 WatchdogPort.list_runner_bridge_status() 查询。port 未注册返回 UNKNOWN。
全 healthy → UP，有 unhealthy → DEGRADED，全 unhealthy → DOWN。

⚠️ **2026-10-16 修正**：本检查原先读 `getattr(s, "is_healthy", None)`，而 `RunnerBridgeStatus`
（`src/core/watchdog/types.py:52`，frozen dataclass）**根本没有 `is_healthy` 字段**
（只有 `last_consecutive_failures` / `cooldown_until` / `is_recovering` / `last_report_time` …）
⇒ 取到恒为 `None` ⇒ **每个 runner 恒判 unhealthy ⇒ 聚合健康永久 DOWN**（真机实测
`{"healthy": 0, "unhealthy": 3}`，而三个 runner 里 napcat 明明在正常工作）。
⇒ 现改为**按真实字段判定**（见 `_is_runner_healthy`）。判据要点：只读类型上确实存在的字段。
"""

from src.core.health_check import BaseHealthCheck, HealthResult, HealthStatus
from src.core.watchdog.types import RunnerBridgeStatus


def _is_runner_healthy(status: RunnerBridgeStatus) -> bool:
    """Runner 是否健康——**按 RunnerBridgeStatus 真实存在的字段判定**。

    依据（`src/core/watchdog/runner_health_bridge.py` 的状态构造点）：
    - 新注册 / 故障恢复后：`last_consecutive_failures=0` 且 `is_recovering=False` ⇒ 健康基线；
    - 发生故障：`last_consecutive_failures` 累加、`cooldown_until` 前推、`is_recovering` 置位。

    ⇒ 判据取「无连续故障 **且** 不在恢复中」。`cooldown_until` 不作为独立判据
    （它只在故障时被设置，故障计数器归零后它已过期或与之一致）。
    """
    return status.last_consecutive_failures == 0 and not status.is_recovering


class WatchdogRunnerHealthCheck(BaseHealthCheck):
    """Runner 健康状态健康检查。"""

    def __init__(self, timeout: float | None = None) -> None:
        super().__init__(name="watchdog.runner_health", timeout=timeout)

    async def _do_check(self) -> HealthResult:
        try:
            from src.core.watchdog_port_registry import get_watchdog_port

            port = get_watchdog_port()
        except RuntimeError:
            return HealthResult(
                HealthStatus.UNKNOWN,
                {"reason": "watchdog port 未注册"},
            )

        statuses = port.list_runner_bridge_status()
        if not statuses:
            return HealthResult(
                HealthStatus.UNKNOWN,
                {"reason": "无 runner 注册"},
            )

        healthy = 0
        unhealthy_ids: list[str] = []
        for s in statuses:
            if _is_runner_healthy(s):
                healthy += 1
            else:
                unhealthy_ids.append(s.runner_id)

        unhealthy = len(unhealthy_ids)
        if unhealthy == 0:
            return HealthResult(HealthStatus.UP, {"healthy": healthy, "unhealthy": 0})
        if healthy == 0:
            return HealthResult(
                HealthStatus.DOWN,
                {"healthy": 0, "unhealthy": unhealthy, "unhealthy_runners": unhealthy_ids},
            )
        return HealthResult(
            HealthStatus.DEGRADED,
            {"healthy": healthy, "unhealthy": unhealthy, "unhealthy_runners": unhealthy_ids},
        )