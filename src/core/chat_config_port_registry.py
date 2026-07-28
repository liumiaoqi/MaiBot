"""ChatConfig 注册点。"""


from typing import Any, Optional

from src.core.protocols import ChatConfigPort
from src.core.startup.types import StartupPhase

_provider: Optional[ChatConfigPort] = None


def get_chat_config_port() -> Optional[ChatConfigPort]:
    return _provider


def set_chat_config_port(port: ChatConfigPort) -> None:
    global _provider
    _provider = port


def reset_chat_config_port() -> None:
    global _provider
    _provider = None


__service_descriptor__: dict[str, Any] = {
    "name": "chat_config_port",
    "phase": StartupPhase.CORE_SERVICES,
    "order": 11,
    "critical": True,
    "protocol": ChatConfigPort,
    "register_fn": set_chat_config_port,
    "depends_on": (),
}
