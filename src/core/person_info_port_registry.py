"""PersonInfoPort 注册点。"""


from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.core.protocols import PersonInfoPort

_provider: Optional[PersonInfoPort] = None


def get_person_info_port() -> Optional[PersonInfoPort]:
    return _provider


def set_person_info_port(port: PersonInfoPort) -> None:
    global _provider
    _provider = port


def reset_person_info_port() -> None:
    global _provider
    _provider = None
