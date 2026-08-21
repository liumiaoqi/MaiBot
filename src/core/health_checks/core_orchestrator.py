"""core.orchestrator 健康检查 — 启动编排状态。

通过 CoreReadinessPort.is_core_ready() 查询。port 未注册返回 UNKNOWN，未就绪返回 DEGRADED。
"""

from src.core.health_check import BaseHealthCheck, HealthResult, HealthStatus
from src.core.service_manager_port_registry import get_core_readiness_port


class CoreOrchestratorHealthCheck(BaseHealthCheck):
    """启动编排状态健康检查。"""

    def __init__(self, timeout: float | None = None) -> None:
        super().__init__(name="core.orchestrator", timeout=timeout)

    async def _do_check(self) -> HealthResult:
        port = get_core_readiness_port()
        if port is None:
            return HealthResult(
                HealthStatus.UNKNOWN,
                {"reason": "core_readiness port 未注册"},
            )
        if port.is_core_ready():
            return HealthResult(HealthStatus.UP, {"core_ready": True})
        readiness = port.get_core_readiness()
        return HealthResult(
            HealthStatus.DEGRADED,
            {"core_ready": False, "readiness": str(readiness)},
        )