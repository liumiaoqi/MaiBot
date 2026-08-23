"""token 估算器——ZG16-2 design 模块 A，ZG-N6 薄委托层。

ZG-N6 迁移：所有估算函数委托 get_token_meter() 单例——统一会计，
常量从 src.core.token_meter.estimate 导入（单一修改源）。

纯函数约束：无 await/网络/IO/状态变更（ZG16-1 教训延续——select_llm_context_messages
是同步函数，估算器在同步调用链中不能 await）。模块级单例查找是 O(1) dict 读，
热路径开销可忽略——"统一会计"目标要求未来只有一个改"。
"""


import json
from typing import TYPE_CHECKING, List

from src.common.logger import get_logger
from src.core.token_meter.estimate import BLOCK_OVERHEAD, CHARS_PER_TOKEN, ROLE_OVERHEAD
from src.core.token_meter.service import get_token_meter

logger = get_logger("maisaka.context.token_estimator")

__all__ = [
    "CHARS_PER_TOKEN",
    "BLOCK_OVERHEAD",
    "ROLE_OVERHEAD",
    "DEFAULT_CONTEXT_WINDOW",
    "estimate_text",
    "estimate_system_prompt",
    "estimate_tools_schema",
    "estimate_message",
    "estimate_messages",
]

if TYPE_CHECKING:
    from src.maisaka.context.messages import LLMContextMessage

DEFAULT_CONTEXT_WINDOW = 65536


def estimate_text(text: str) -> int:
    """估算纯文本 token 数——委托 TokenMeter 单例。

    Args:
        text: 待估算文本。

    Returns:
        token 估算值；空文本返回 0。
    """
    return get_token_meter().estimate_text(text)


def estimate_system_prompt(system_prompt: str) -> int:
    """估算 system prompt token 数（含结构开销）。"""
    return estimate_text(system_prompt) + BLOCK_OVERHEAD


def estimate_tools_schema(tools: list) -> int:
    """估算 tools schema token 数（含结构开销）。"""
    return estimate_text(json.dumps(tools, ensure_ascii=False, default=str)) + BLOCK_OVERHEAD


def estimate_message(
    message: "LLMContextMessage",
    *,
    enable_visual_message: bool = True,
) -> int:
    """估算单条消息 token 数——委托 TokenMeter 单例。

    Args:
        message: 待估算消息。
        enable_visual_message: 视觉消息开关（轻量近似不依赖此参数，保留接口一致性）。

    Returns:
        token 估算值；空消息返回 ROLE_OVERHEAD + BLOCK_OVERHEAD。
    """
    return get_token_meter().estimate(message)


def estimate_messages(
    messages: List["LLMContextMessage"],
    *,
    enable_visual_message: bool = True,
) -> int:
    """估算多条消息 token 总量（逐条累加）——委托 TokenMeter 单例。"""
    meter = get_token_meter()
    return sum(meter.estimate(msg) for msg in messages)
