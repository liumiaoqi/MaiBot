"""EventBus 注册点。"""


from typing import Any, Optional

from src.core.protocols import AutonomyEventBusPort
from src.core.startup.types import StartupPhase

_provider: Optional[AutonomyEventBusPort] = None


def get_event_bus_port() -> Optional[AutonomyEventBusPort]:
    return _provider


def set_event_bus_port(port: AutonomyEventBusPort) -> None:
    global _provider
    _provider = port


def reset_event_bus_port() -> None:
    global _provider
    _provider = None


# 已废弃（ZG-10 T31）：启动项元数据已由 @startup_item/StartupItemDesc 承载。
# 保留仅为过渡期兼容，禁止新代码读取。
__service_descriptor__: dict[str, Any] = {
    "name": "event_bus_port",
    "phase": StartupPhase.CORE_SERVICES,
    "order": 13,
    "critical": True,
    "protocol": AutonomyEventBusPort,
    "register_fn": set_event_bus_port,
    "depends_on": (),
}
