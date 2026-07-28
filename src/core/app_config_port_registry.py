"""AppConfig 注册点。"""


from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.core.protocols import AppConfigPort

_provider: Optional[AppConfigPort] = None


def get_app_config_port() -> Optional[AppConfigPort]:
    return _provider


def set_app_config_port(port: AppConfigPort) -> None:
    global _provider
    _provider = port


def reset_app_config_port() -> None:
    global _provider
    _provider = None
