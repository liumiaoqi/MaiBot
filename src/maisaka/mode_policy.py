"""Maisaka Planner-only 模式策略。"""

from src.core.chat_config_port_registry import get_chat_config_port

IDLE_CYCLE_REASONS = {"planner_no_tool_end", "planner_wait_rest", "tool_pause:wait"}


def get_reply_trigger_mode() -> str:
    """读取当前回复触发模式。"""

    return get_chat_config_port().get_reply_timing_config().reply_trigger_mode


def is_reply_necessity_trigger_enabled() -> bool:
    """判断是否启用回复必要性触发门。"""

    return get_reply_trigger_mode() == "reply_necessity"


def is_idle_cycle_reason(cycle_end_reason: str) -> bool:
    """判断整轮结束原因是否属于空闲退避。"""

    return str(cycle_end_reason).strip() in IDLE_CYCLE_REASONS
