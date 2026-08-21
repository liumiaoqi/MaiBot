"""service_manager 不变量 — service registry 全非 None 且状态合法。

通过 ServiceManagerPort.list_states() 查询，只读内存。
"""

from src.core.invariant_registry import invariant
from src.core.service_manager_port_registry import get_service_manager_port


@invariant("service_manager")
def check_service_manager(fail) -> None:
    """检查 service registry 组件状态合法。"""
    port = get_service_manager_port()
    if port is None:
        fail("service_manager port 未注册")
        return
    states = port.list_states()
    for snapshot in states:
        if snapshot is None:
            fail("service_registry 含 None 状态")
            continue
        state_str = str(getattr(snapshot, "state", "")).lower()
        if state_str and state_str not in ("running", "degraded", "stopped", "pending", "initialized"):
            fail(f"组件状态非法: {snapshot}")