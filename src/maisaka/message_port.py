"""核心消息端口 — 向后兼容重导出。

MessagePortV2 Protocol 定义在 src.core.protocols，
SendServiceMessagePortV2 实现在 src.services.send_service，
注册点在 src.core.message_port_registry。
此文件保留重导出以兼容旧导入路径。
"""

from src.core.message_port_registry import get_message_port_v2, set_message_port_v2
from src.core.protocols import MessagePortV2

__all__ = [
    "MessagePortV2",
    "SendServiceMessagePortV2",
    "get_message_port_v2",
    "set_message_port_v2",
]


def __getattr__(name: str):
    if name == "SendServiceMessagePortV2":
        from src.services.send_service import SendServiceMessagePortV2
        return SendServiceMessagePortV2
    if name in ("MessagePort", "SendServicePort", "BridgedMessagePortV2",
                "get_message_port", "set_message_port"):
        raise AttributeError(
            f"{name} 已在回复系统迁移中移除，请使用 MessagePortV2 / get_message_port_v2()"
        )
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
