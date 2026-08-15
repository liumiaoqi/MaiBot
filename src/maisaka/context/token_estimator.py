"""token 估算器（纯函数，无副作用）——ZG16-2 design 模块 A。

固定 2 字符/token（dsh 拍板决策 1，中文略高估英文略低估偏安全）+ 结构开销复用 dsh
（BLOCK_OVERHEAD=4/ROLE_OVERHEAD=4）。计量对象 = ZG16-1 文本投影（占位符语义）。

纯函数约束：无 await/网络/IO/状态变更（ZG16-1 教训延续——select_llm_context_messages
是同步函数，估算器在同步调用链中不能 await）。
"""


import json
import math
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from src.maisaka.context.messages import LLMContextMessage

CHARS_PER_TOKEN = 2
BLOCK_OVERHEAD = 4
ROLE_OVERHEAD = 4
DEFAULT_CONTEXT_WINDOW = 65536


def estimate_text(text: str) -> int:
    """估算纯文本 token 数。

    Args:
        text: 待估算文本。

    Returns:
        token 估算值；空文本返回 0。
    """
    if not text:
        return 0
    return math.ceil(len(text) / CHARS_PER_TOKEN)


def estimate_system_prompt(system_prompt: str) -> int:
    """估算 system prompt token 数（含结构开销）。"""
    return estimate_text(system_prompt) + BLOCK_OVERHEAD


def estimate_tools_schema(tools: list) -> int:
    """估算 tools schema token 数（含结构开销）。"""
    return estimate_text(json.dumps(tools, ensure_ascii=False)) + BLOCK_OVERHEAD


def _get_lightweight_projection(message: "LLMContextMessage") -> str:
    """取轻量近似文本（processed_plain_text，已含 ZG16-1 占位符语义）。

    占位符替换失败降级用空字符串兜底，不崩溃（spec 5.1.3 异常 2）。
    """
    try:
        return getattr(message, "processed_plain_text", "") or ""
    except Exception:
        return ""


def estimate_message(
    message: "LLMContextMessage",
    *,
    enable_visual_message: bool = True,
) -> int:
    """估算单条消息 token 数（轻量近似 + 结构开销）。

    用 processed_plain_text 做近似文本（已含占位符语义），不调完整
    _build_message_from_sequence 投影（select 是热路径，完整投影开销大）。

    Args:
        message: 待估算消息。
        enable_visual_message: 视觉消息开关（轻量近似不依赖此参数，保留接口一致性）。

    Returns:
        token 估算值；空消息返回 ROLE_OVERHEAD + BLOCK_OVERHEAD。
    """
    projection = _get_lightweight_projection(message)
    return estimate_text(projection) + BLOCK_OVERHEAD + ROLE_OVERHEAD


def estimate_messages(
    messages: List["LLMContextMessage"],
    *,
    enable_visual_message: bool = True,
) -> int:
    """估算多条消息 token 总量（逐条累加）。"""
    return sum(
        estimate_message(msg, enable_visual_message=enable_visual_message)
        for msg in messages
    )