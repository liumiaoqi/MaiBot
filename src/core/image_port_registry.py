"""ImageDescriptionPort 注册点。"""

from typing import Any, Optional

_port: Any = None


def register_image_description_port(port: Any) -> None:
    global _port
    _port = port


def get_image_description_port() -> Optional[Any]:
    return _port
