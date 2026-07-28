"""ModelConfigPort 注册点。"""


from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.core.protocols import ModelConfigPort

_provider: Optional[ModelConfigPort] = None


def get_model_config_port() -> Optional[ModelConfigPort]:
    return _provider


def register_model_config_port(port: ModelConfigPort) -> None:
    global _provider
    _provider = port


def reset_model_config_port() -> None:
    global _provider
    _provider = None
