"""全局 MessagePort 注册点。

核心模块通过 get_message_port() 获取 MessagePort 实例，
不直接依赖 send_service 或其他组件。
"""

from __future__ import annotations

from typing import Optional

from src.core.protocols import MessagePort

_port_instance: Optional[MessagePort] = None


def get_message_port() -> MessagePort:
    """获取全局 MessagePort 实例。"""
    global _port_instance
    if _port_instance is None:
        from src.core.adapters.message_port import SendServicePort
        _port_instance = SendServicePort()
    return _port_instance


def set_message_port(port: MessagePort) -> None:
    """设置全局 MessagePort 实例（用于测试或替换实现）。"""
    global _port_instance
    _port_instance = port