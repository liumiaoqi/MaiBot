"""全局 MessagePort 注册点。

核心模块通过 get_message_port() 获取 MessagePort 实例，
不直接依赖 send_service 或其他组件。
"""

from __future__ import annotations

from typing import Optional

from src.core.protocols import MessagePort, MessagePortV2

_port_instance: Optional[MessagePort] = None
_port_v2_instance: Optional[MessagePortV2] = None


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


def get_message_port_v2() -> MessagePortV2:
    """获取全局 MessagePortV2 实例。"""
    global _port_v2_instance
    if _port_v2_instance is None:
        from src.core.adapters.message_port_v2 import BridgedMessagePortV2
        _port_v2_instance = BridgedMessagePortV2()
    return _port_v2_instance


def set_message_port_v2(port: MessagePortV2) -> None:
    """设置全局 MessagePortV2 实例（用于测试或替换实现）。"""
    global _port_v2_instance
    _port_v2_instance = port