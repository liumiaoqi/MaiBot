"""ZG-N6 统一 Token 计量服务——固定启发式纯函数。

对齐 dsh `@deepseek-ai/dsh-token-meter` 的 estimate.ts。
固定启发式：每 token ≈ 4 字符 + 结构开销，有意无配置（dsh validateConfigKeys 哲学）。
CJK 低估已知不修（对齐 dsh 已知限制）。

纯函数约束：无 await/网络/IO/状态变更。
"""

import json
import math
from typing import Any, Sequence

CHARS_PER_TOKEN: int = 4
BLOCK_OVERHEAD: int = 4
ROLE_OVERHEAD: int = 4


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


def _extract_block_text(block: Any) -> str:
    """从 block 提取文本——按 block 类型递归提取。

    支持 dict 和对象属性两种形式。未知 block 转 JSON 后启发式计价。
    """
    if isinstance(block, str):
        return block

    if isinstance(block, dict):
        block_type = block.get("type", "")

        if block_type == "text":
            return str(block.get("text", ""))
        if block_type == "reasoning":
            return str(block.get("reasoning", block.get("thinking", "")))
        if block_type == "tool_call":
            name = str(block.get("name", ""))
            arguments = block.get("arguments", block.get("input", ""))
            if not isinstance(arguments, str):
                arguments = json.dumps(arguments, ensure_ascii=False)
            return name + str(arguments)
        if block_type == "tool_result":
            content = block.get("content", block.get("result", ""))
            if isinstance(content, list):
                return str(estimate_content(content))
            return str(content)

        return json.dumps(block, ensure_ascii=False, default=str)

    if hasattr(block, "type"):
        block_type = getattr(block, "type", "")

        if block_type == "text":
            return str(getattr(block, "text", ""))
        if block_type == "reasoning":
            return str(getattr(block, "reasoning", getattr(block, "thinking", "")))
        if block_type == "tool_call":
            name = str(getattr(block, "name", ""))
            arguments = getattr(block, "arguments", getattr(block, "input", ""))
            if not isinstance(arguments, str):
                arguments = json.dumps(arguments, ensure_ascii=False, default=str)
            return name + str(arguments)
        if block_type == "tool_result":
            content = getattr(block, "content", getattr(block, "result", ""))
            if isinstance(content, list):
                return str(estimate_content(content))
            return str(content)

    return json.dumps(block, ensure_ascii=False, default=str)


def estimate_content(blocks: Sequence[Any]) -> int:
    """估算 content blocks token 数（按 block 类型递归累加 + 每块结构开销）。

    Args:
        blocks: content block 序列。

    Returns:
        token 估算值；空序列返回 0。
    """
    if not blocks:
        return 0
    total = 0
    for block in blocks:
        text = _extract_block_text(block)
        total += estimate_text(text) + BLOCK_OVERHEAD
    return total


def estimate_message(message: Any) -> int:
    """估算单条消息 token 数（含角色 + 块结构开销）。

    支持多种消息格式：
    - 含 content 属性（list/sequence）→ estimate_content + ROLE_OVERHEAD
    - 含 processed_plain_text 属性 → estimate_text + BLOCK_OVERHEAD + ROLE_OVERHEAD
    - 纯字符串 → estimate_text
    - dict 含 content 键 → estimate_content + ROLE_OVERHEAD
    - 未知 → str(message) 后启发式计价 + 结构开销

    缺失字段按空处理，不抛异常（对齐 dsh 降级而非崩溃）。

    Args:
        message: 待估算消息。

    Returns:
        token 估算值；空消息返回 ROLE_OVERHEAD + BLOCK_OVERHEAD = 8。
    """
    if message is None:
        return ROLE_OVERHEAD + BLOCK_OVERHEAD

    if isinstance(message, str):
        return estimate_text(message)

    if isinstance(message, dict):
        content = message.get("content")
        if content is not None:
            if isinstance(content, str):
                return estimate_text(content) + BLOCK_OVERHEAD + ROLE_OVERHEAD
            if isinstance(content, list):
                return estimate_content(content) + ROLE_OVERHEAD
        text = message.get("text")
        if text is not None:
            return estimate_text(str(text)) + BLOCK_OVERHEAD + ROLE_OVERHEAD
        return estimate_text(json.dumps(message, ensure_ascii=False, default=str)) + ROLE_OVERHEAD

    try:
        content = getattr(message, "content", None)
        if content is not None:
            if isinstance(content, str):
                return estimate_text(content) + BLOCK_OVERHEAD + ROLE_OVERHEAD
            if isinstance(content, list):
                return estimate_content(content) + ROLE_OVERHEAD

        projection = getattr(message, "processed_plain_text", None)
        if projection is not None:
            return estimate_text(str(projection)) + BLOCK_OVERHEAD + ROLE_OVERHEAD

        text = getattr(message, "text", None)
        if text is not None:
            return estimate_text(str(text)) + BLOCK_OVERHEAD + ROLE_OVERHEAD
    except Exception:
        pass

    return estimate_text(str(message)) + ROLE_OVERHEAD + BLOCK_OVERHEAD


def estimate_system_prompt(system_prompt: str) -> int:
    """估算 system prompt token 数（含结构开销）。"""
    return estimate_text(system_prompt) + BLOCK_OVERHEAD


def estimate_tools_schema(tools: list) -> int:
    """估算 tools schema token 数（含结构开销）。"""
    return estimate_text(json.dumps(tools, ensure_ascii=False, default=str)) + BLOCK_OVERHEAD