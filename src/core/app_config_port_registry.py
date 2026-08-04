"""AppConfig 注册点。"""


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


# 已废弃（ZG-10 T31）：启动项元数据已由 @startup_item/StartupItemDesc 承载。
# 保留仅为过渡期兼容，禁止新代码读取。
__service_descriptor__: dict[str, Any] = {
    "name": "app_config_port",
    "phase": StartupPhase.CORE_SERVICES,
    "order": 12,
    "critical": True,
    "protocol": AppConfigPort,
    "register_fn": set_app_config_port,
    "depends_on": (),
}
