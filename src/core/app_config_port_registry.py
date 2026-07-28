"""AppConfig 注册点。"""

from __future__ import annotations

from typing import Any, Optional

from src.core.protocols import AppConfigPort
from src.core.startup.types import StartupPhase

_provider: Optional[AppConfigPort] = None


def get_app_config_port() -> Optional[AppConfigPort]:
    return _provider


def set_app_config_port(port: AppConfigPort) -> None:
    global _provider
    _provider = port


def reset_app_config_port() -> None:
    global _provider
    _provider = None


__service_descriptor__: dict[str, Any] = {
    "name": "app_config_port",
    "phase": StartupPhase.CORE_SERVICES,
    "order": 12,
    "critical": True,
    "protocol": AppConfigPort,
    "register_fn": set_app_config_port,
    "depends_on": (),
}
