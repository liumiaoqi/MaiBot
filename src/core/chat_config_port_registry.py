"""ChatConfig 注册点。"""


from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.core.protocols import ChatConfigPort

_provider: Optional[ChatConfigPort] = None


def get_chat_config_port() -> Optional[ChatConfigPort]:
    return _provider


def set_chat_config_port(port: ChatConfigPort) -> None:
    global _provider
    _provider = port


def reset_chat_config_port() -> None:
    global _provider
    _provider = None
