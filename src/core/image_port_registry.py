"""ImageDescriptionPort 注册点。"""


from typing import Any, Optional

from src.core.protocols import ImageDescriptionPort
from src.core.startup.types import StartupPhase

_port: Any = None


def register_image_description_port(port: Any) -> None:
    global _port
    _port = port


def get_image_description_port() -> Optional[Any]:
    return _port


__service_descriptor__: dict[str, Any] = {
    "name": "image_port",
    "phase": StartupPhase.CORE_SERVICES,
    "order": 4,
    "critical": True,
    "protocol": ImageDescriptionPort,
    "register_fn": register_image_description_port,
    "depends_on": (),
}
