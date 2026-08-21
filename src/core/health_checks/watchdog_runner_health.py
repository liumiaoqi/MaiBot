"""watchdog.runner_health 健康检查 — Runner 健康状态。

通过 WatchdogPort.list_runner_bridge_status() 查询。port 未注册返回 UNKNOWN。
全 healthy → UP，有 unhealthy → DEGRADED，全 unhealthy → DOWN。
"""

from src.core.health_check import BaseHealthCheck, HealthResult, HealthStatus


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
        unhealthy = 0
        for s in statuses:
            is_healthy = getattr(s, "is_healthy", None)
            if is_healthy:
                healthy += 1
            else:
                unhealthy += 1

        if unhealthy == 0:
            return HealthResult(HealthStatus.UP, {"healthy": healthy, "unhealthy": 0})
        if healthy == 0:
            return HealthResult(HealthStatus.DOWN, {"healthy": 0, "unhealthy": unhealthy})
        return HealthResult(
            HealthStatus.DEGRADED,
            {"healthy": healthy, "unhealthy": unhealthy},
        )