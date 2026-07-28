"""WebUI 聊天广播端口全局注册点 — chat 层通过此注册点获取 WebUI 广播能力，不直接导入 webui 内部模块。"""

from __future__ import annotations

from typing import Any, Callable, Optional

from src.core.startup.types import StartupPhase

_broadcast_fn: Optional[Callable[..., Any]] = None
_platform_name: Optional[str] = None


def register_webui_chat_broadcast(broadcast_fn: Callable[..., Any], platform_name: str) -> None:
    """注册 WebUI 广播函数（webui 启动时调用一次）。"""
    global _broadcast_fn, _platform_name
    _broadcast_fn = broadcast_fn
    _platform_name = platform_name


def get_webui_broadcast_fn() -> Optional[Callable[..., Any]]:
    """获取 WebUI 广播函数。"""
    return _broadcast_fn


def get_webui_platform_name() -> Optional[str]:
    """获取 WebUI 平台名称。"""
    return _platform_name


__service_descriptor__: dict[str, Any] = {
    "name": "webui_chat_broadcast",
    "phase": StartupPhase.READY,
    "order": 99,  # 不经过 main.py，在 webui/app.py 内部注册
    "critical": False,
    "protocol": None,  # 广播函数，非 Protocol
    "register_fn": register_webui_chat_broadcast,
    "depends_on": (),
}
