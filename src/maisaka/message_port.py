"""核心消息端口 — 向后兼容重导出。

MessagePort Protocol 定义已迁移到 src.core.protocols，
SendServicePort 实现已迁移到 src.core.adapters.message_port，
注册点已迁移到 src.core.message_port_registry。
此文件保留重导出以兼容旧导入路径。
"""

from src.core.message_port_registry import get_message_port, set_message_port
from src.core.protocols import MessagePort

__all__ = ["MessagePort", "SendServicePort", "get_message_port", "set_message_port"]


def __getattr__(name: str):
    if name == "SendServicePort":
        from src.core.adapters.message_port import SendServicePort
        return SendServicePort
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
