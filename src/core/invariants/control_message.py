"""control_message 不变量 — control message port 已注册。

get_control_message_port() 未注册时抛 RuntimeError，捕获为违反。
"""

from src.core.invariant_registry import invariant


@invariant("control_message")
def check_control_message(fail) -> None:
    """检查 control message port 已注册。"""
    try:
        from src.core.control_message_port_registry import get_control_message_port

        get_control_message_port()
    except RuntimeError as exc:
        fail(f"control_message port 未注册: {exc}")