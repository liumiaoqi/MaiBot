"""ReplyerServicePort 注册点。"""

from __future__ import annotations

from typing import Any, Optional

from src.core.protocols import ReplyerServicePort
from src.core.startup.types import StartupPhase

_port: Any = None


def register_replyer_service_port(port: Any) -> None:
    global _port
    _port = port


def get_replyer_service_port() -> Optional[Any]:
    return _port


__service_descriptor__: dict[str, Any] = {
    "name": "replyer_port",
    "phase": StartupPhase.CORE_SERVICES,
    "order": 3,
    "critical": True,
    "protocol": ReplyerServicePort,
    "register_fn": register_replyer_service_port,
    "depends_on": (),
}
