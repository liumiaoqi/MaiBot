"""ImageDescriptionPort 注册点。"""


from typing import Any, Optional

from src.core.protocols import ImageDescriptionPort
from src.core.startup.types import StartupPhase

_port: Any = None


def register_image_description_port(port: Any) -> None:
    global _port
    _port = port


def get_image_description_port() -> Optional[Any]:
    return _port


# 已废弃（ZG-10 T31）：启动项元数据已由 @startup_item/StartupItemDesc 承载。
# 保留仅为过渡期兼容，禁止新代码读取。
__service_descriptor__: dict[str, Any] = {
    "name": "image_port",
    "phase": StartupPhase.CORE_SERVICES,
    "order": 4,
    "critical": True,
    "protocol": ImageDescriptionPort,
    "register_fn": register_image_description_port,
    "depends_on": (),
}
