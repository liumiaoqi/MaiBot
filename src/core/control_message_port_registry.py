"""ControlMessagePort 注册点（ZG-8）。

供 main.py 注册、消息处理路径/WebUI 查询。未注册时 get_control_message_port 抛
RuntimeError（调用方应捕获并降级，保持渐进启用透明性）。
"""


from typing import Optional

from src.core.protocols import ControlMessagePort

_control_message_port: Optional[ControlMessagePort] = None


def get_control_message_port() -> ControlMessagePort:
    """获取已注册的 ControlMessagePort 实例。

    Returns:
        ControlMessagePort 实例

    Raises:
        RuntimeError: ControlMessagePort 未注册
    """
    if _control_message_port is None:
        raise RuntimeError("ControlMessagePort 未注册")
    return _control_message_port


def set_control_message_port(port: ControlMessagePort) -> None:
    """注册 ControlMessagePort 实例。

    Args:
        port: ControlMessagePort 实例（后注册覆盖）
    """
    global _control_message_port
    _control_message_port = port


def reset_control_message_port() -> None:
    """清空注册（测试用）。"""
    global _control_message_port
    _control_message_port = None
