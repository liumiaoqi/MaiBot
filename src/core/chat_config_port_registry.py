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


# 已废弃（ZG-10 T31）：启动项元数据已由 @startup_item/StartupItemDesc 承载。
# 保留仅为过渡期兼容，禁止新代码读取。
__service_descriptor__: dict[str, Any] = {
    "name": "chat_config_port",
    "phase": StartupPhase.CORE_SERVICES,
    "order": 11,
    "critical": True,
    "protocol": ChatConfigPort,
    "register_fn": set_chat_config_port,
    "depends_on": (),
}
