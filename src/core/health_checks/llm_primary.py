"""llm.primary 健康检查 — 主 LLM 可达性。

v2 简化：检查 model_config port 已注册。v3 增强：查 last_success_time。
"""

import time

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
        # v3：查 last_success_time
        last_success = port.get_last_success_time()
        if last_success is None:
            return HealthResult(HealthStatus.DEGRADED, {"reason": "无成功调用记录"})
        if time.time() - last_success > 300:
            return HealthResult(HealthStatus.DEGRADED, {"reason": "最近 5 分钟无成功调用"})
        return HealthResult(HealthStatus.UP, {"last_success": last_success})