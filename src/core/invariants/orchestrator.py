"""core.orchestrator 不变量 — 核心就绪三标志全 True 或标注 DEGRADED。

通过 CoreReadinessPort 查询，只读内存快照。
"""

from src.core.invariant_registry import invariant
from src.core.service_manager_port_registry import get_core_readiness_port


@invariant("core.orchestrator")
def check_orchestrator(fail) -> None:
    """检查核心就绪三标志。"""
    port = get_core_readiness_port()
    if port is None:
        fail("core_readiness port 未注册")
        return
    if not port.is_core_ready():
        readiness = port.get_core_readiness()
        fail(f"核心未就绪: {readiness}")