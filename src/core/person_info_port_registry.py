"""PersonInfoPort 注册点。"""


from typing import Any, Optional

from src.core.protocols import PersonInfoPort
from src.core.startup.types import StartupPhase

_provider: Optional[PersonInfoPort] = None


def get_person_info_port() -> Optional[PersonInfoPort]:
    return _provider


def set_person_info_port(port: PersonInfoPort) -> None:
    global _provider
    _provider = port


def reset_person_info_port() -> None:
    global _provider
    _provider = None


# 已废弃（ZG-10 T31）：启动项元数据已由 @startup_item/StartupItemDesc 承载。
# 保留仅为过渡期兼容，禁止新代码读取。
__service_descriptor__: dict[str, Any] = {
    "name": "person_info_port",
    "phase": StartupPhase.CORE_SERVICES,
    "order": 9,
    "critical": True,
    "protocol": PersonInfoPort,
    "register_fn": set_person_info_port,
    "depends_on": (),
}
