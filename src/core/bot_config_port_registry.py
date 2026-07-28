"""BotConfig 注册点。"""


from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.core.protocols import BotConfigPort

_provider: Optional[BotConfigPort] = None


def get_bot_config_port() -> Optional[BotConfigPort]:
    return _provider


def set_bot_config_port(port: BotConfigPort) -> None:
    global _provider
    _provider = port


def reset_bot_config_port() -> None:
    global _provider
    _provider = None
