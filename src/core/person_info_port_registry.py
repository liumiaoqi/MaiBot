"""PersonInfoPort 注册点。"""


from typing import Any, Optional

from src.core.protocols import PersonInfoPort
from src.core.startup.types import StartupPhase

_provider: Optional[PersonInfoPort] = None


def get_person_info_port() -> Optional[PersonInfoPort]:
    return _provider


def set_person_info_port(port: PersonInfoPort) -> None:
    global _provider
    _provider = port


def reset_person_info_port() -> None:
    global _provider
    _provider = None


__service_descriptor__: dict[str, Any] = {
    "name": "person_info_port",
    "phase": StartupPhase.CORE_SERVICES,
    "order": 9,
    "critical": True,
    "protocol": PersonInfoPort,
    "register_fn": set_person_info_port,
    "depends_on": (),
}
