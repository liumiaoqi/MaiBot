"""ReplyerServicePort 注册点。"""


from typing import Any, Optional

from src.core.protocols import ReplyerServicePort
from src.core.startup.types import StartupPhase

_port: Any = None


def register_replyer_service_port(port: Any) -> None:
    global _port
    _port = port


def get_replyer_service_port() -> Optional[Any]:
    return _port


# 已废弃（ZG-10 T31）：启动项元数据已由 @startup_item/StartupItemDesc 承载。
# 保留仅为过渡期兼容，禁止新代码读取。
__service_descriptor__: dict[str, Any] = {
    "name": "replyer_port",
    "phase": StartupPhase.CORE_SERVICES,
    "order": 3,
    "critical": True,
    "protocol": ReplyerServicePort,
    "register_fn": register_replyer_service_port,
    "depends_on": (),
}
