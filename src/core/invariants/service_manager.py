"""service_manager 不变量 — service registry 全非 None 且状态合法。

通过 ServiceManagerPort.list_states() 查询，只读内存。
"""

from src.core.invariant_registry import invariant
from src.core.service_manager.types import ServiceState
from src.core.service_manager_port_registry import get_service_manager_port

# 合法状态白名单——用 frozenset(ServiceState) 自动跟随枚举定义，
# 避免 str(Enum) 行为差异（Python 3.11+ str(Enum) 返回 repr 而非 value）和白名单与枚举失同步
_VALID_STATES = frozenset(ServiceState)


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
        state = getattr(snapshot, "state", None)
        if state is None:
            fail(f"服务状态未知: {snapshot}")
            continue
        if state not in _VALID_STATES:
            fail(f"组件状态非法: {snapshot}")