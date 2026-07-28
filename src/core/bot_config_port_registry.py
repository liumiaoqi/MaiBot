"""BotConfig 注册点。"""

from __future__ import annotations

from typing import Any, Optional

from src.core.protocols import BotConfigPort
from src.core.startup.types import StartupPhase

_provider: Optional[BotConfigPort] = None


def get_bot_config_port() -> Optional[BotConfigPort]:
    return _provider


def set_bot_config_port(port: BotConfigPort) -> None:
    global _provider
    _provider = port


def reset_bot_config_port() -> None:
    global _provider
    _provider = None


__service_descriptor__: dict[str, Any] = {
    "name": "bot_config_port",
    "phase": StartupPhase.CORE_SERVICES,
    "order": 10,
    "critical": True,
    "protocol": BotConfigPort,
    "register_fn": set_bot_config_port,
    "depends_on": (),
}
