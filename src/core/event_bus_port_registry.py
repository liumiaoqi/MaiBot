"""EventBus 注册点。"""


from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.core.protocols import AutonomyEventBusPort

_provider: Optional[AutonomyEventBusPort] = None


def get_event_bus_port() -> Optional[AutonomyEventBusPort]:
    return _provider


def set_event_bus_port(port: AutonomyEventBusPort) -> None:
    global _provider
    _provider = port


def reset_event_bus_port() -> None:
    global _provider
    _provider = None
