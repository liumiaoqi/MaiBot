"""ReplyerServicePort 注册点。"""

from typing import Any, Optional

_port: Any = None


def register_replyer_service_port(port: Any) -> None:
    global _port
    _port = port


def get_replyer_service_port() -> Optional[Any]:
    return _port
