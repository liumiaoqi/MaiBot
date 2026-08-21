"""plugin.runtime 健康检查 — 插件运行时状态机。

通过 IpcBridgePort.is_running 查询。port 未注册返回 UNKNOWN，未启动返回 DEGRADED。
"""

from src.core.health_check import BaseHealthCheck, HealthResult, HealthStatus
from src.core.ipc_bridge_port_registry import get_ipc_bridge_port


class PluginRuntimeHealthCheck(BaseHealthCheck):
    """插件运行时状态健康检查。"""

    timeout = 1.0

    def __init__(self, timeout: float | None = None) -> None:
        super().__init__(name="plugin.runtime", timeout=timeout or 1.0)

    async def _do_check(self) -> HealthResult:
        port = get_ipc_bridge_port()
        if port is None:
            return HealthResult(
                HealthStatus.UNKNOWN,
                {"reason": "ipc_bridge port 未注册"},
            )
        # v3：插件状态机检查
        states = port.list_plugin_states()
        if not states:
            return HealthResult(HealthStatus.UNKNOWN, {"reason": "无插件注册"})
        errored = [s for s in states if s.state == "error"]
        if errored:
            return HealthResult(HealthStatus.DOWN, {"errored": len(errored)})
        if not port.is_running:
            return HealthResult(HealthStatus.DEGRADED, {"is_running": False, "reason": "插件运行时未启动"})
        return HealthResult(HealthStatus.UP, {"plugins": len(states)})