"""ModelConfigPort 注册点。"""


from typing import Any, Optional

from src.core.protocols import ModelConfigPort
from src.core.startup.types import StartupPhase

_provider: Optional[ModelConfigPort] = None


def get_model_config_port() -> Optional[ModelConfigPort]:
    return _provider


def register_model_config_port(port: ModelConfigPort) -> None:
    global _provider
    _provider = port


def reset_model_config_port() -> None:
    global _provider
    _provider = None


__service_descriptor__: dict[str, Any] = {
    "name": "model_config_port",
    "phase": StartupPhase.CORE_SERVICES,
    "order": 6,
    "critical": True,
    "protocol": ModelConfigPort,
    "register_fn": register_model_config_port,
    "depends_on": ("agent_registry",),
}
