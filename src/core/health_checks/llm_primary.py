"""llm.primary 健康检查 — 主 LLM 可达性。

v2 简化：检查 model_config port 已注册。v3 增强：查 last_success_time。
"""

from src.core.health_check import BaseHealthCheck, HealthResult, HealthStatus
from src.core.model_config_port_registry import get_model_config_port


class LlmPrimaryHealthCheck(BaseHealthCheck):
    """主 LLM 可达性健康检查。"""

    def __init__(self, timeout: float | None = None) -> None:
        super().__init__(name="llm.primary", timeout=timeout)

    async def _do_check(self) -> HealthResult:
        port = get_model_config_port()
        if port is None:
            return HealthResult(
                HealthStatus.UNKNOWN,
                {"reason": "model_config port 未注册（LLM 可能未配置）"},
            )
        return HealthResult(HealthStatus.UP, {"port": type(port).__name__})