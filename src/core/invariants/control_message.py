"""control_message 不变量 — control message port 已注册。

get_control_message_port() 未注册时抛 RuntimeError，捕获为违反。

⚠️ 启动时序：本 port 由 `MainSystem._init_components` 收尾的 ZG-8 接线注册，
晚于启动编排（`orchestrator.run()`）内的启动检查 ⇒ 接线窗口内该失败记为
"待接线"（见 invariant_registry.open_startup_wiring），窗口关闭时仍缺才是违反。
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