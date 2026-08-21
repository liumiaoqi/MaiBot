"""chat.session_store 健康检查 — 会话存储一致性。

通过 SessionInfoPort 查询。port 未注册返回 DOWN（session 是核心必需组件，区别于 A_memorix 的 UNKNOWN）。
"""

from src.core.health_check import BaseHealthCheck, HealthResult, HealthStatus
from src.core.session_port_registry import get_session_info_port


class ChatSessionStoreHealthCheck(BaseHealthCheck):
    """会话存储一致性健康检查。"""

    timeout = 1.0

    def __init__(self, timeout: float | None = None) -> None:
        super().__init__(name="chat.session_store", timeout=timeout or 1.0)

    async def _do_check(self) -> HealthResult:
        port = get_session_info_port()
        if port is None:
            return HealthResult(
                HealthStatus.DOWN,
                {"reason": "session info port 未注册（session 是核心必需组件）"},
            )
        return HealthResult(HealthStatus.UP, {"port": type(port).__name__})