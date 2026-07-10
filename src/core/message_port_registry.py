"""全局 MessagePortV2 注册点。

核心模块通过 get_message_port_v2() 获取 MessagePortV2 实例，
不直接依赖 send_service 或其他组件。
"""

from __future__ import annotations

from typing import Optional

from src.core.protocols import MessagePortV2

_port_v2_instance: Optional[MessagePortV2] = None


def get_message_port_v2() -> MessagePortV2:
    """获取全局 MessagePortV2 实例。"""
    global _port_v2_instance
    if _port_v2_instance is None:
        from src.services.send_service import SendServiceMessagePortV2
        _port_v2_instance = SendServiceMessagePortV2()
    return _port_v2_instance


def set_message_port_v2(port: MessagePortV2) -> None:
    """设置全局 MessagePortV2 实例（用于测试或替换实现）。"""
    global _port_v2_instance
    _port_v2_instance = port
