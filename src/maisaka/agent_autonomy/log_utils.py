"""智能体自主性日志工具 — 统一的日志格式辅助。"""

from __future__ import annotations

from typing import Optional

from src.common.logger import get_logger
logger = get_logger("agent_autonomy.log_utils")



def fmt_agent(agent_id: str, display_name: str = "", session_name: str = "") -> str:
    """构建统一的智能体标识字符串。

    Returns:
        如 "agent=silver_wolf(银狼)" 或 "agent=silver_wolf"
    """
    if display_name:
        return f"agent={agent_id}({display_name})"
    return f"agent={agent_id}"


def fmt_event(
    agent_id: str,
    event: str,
    *,
    display_name: str = "",
    session_name: str = "",
    extra: str = "",
) -> str:
    """构建统一的事件日志格式。

    Format: [Autonomy:agent] event detail session=X

    Returns:
        格式化的日志消息。
    """
    parts = [f"[Autonomy:{agent_id}]", event]
    if display_name:
        parts[0] = f"[Autonomy:{agent_id}({display_name})]"
    if extra:
        parts.append(extra)
    if session_name:
        parts.append(f"session={session_name}")
    return " ".join(parts)


def fmt_butler(
    event: str,
    *,
    butler_id: str = "rita",
    butler_name: str = "丽塔",
    session_name: str = "",
    extra: str = "",
) -> str:
    """构建管家事件日志格式。

    Format: [Butler:rita(丽塔)] event detail
    """
    parts = [f"[Butler:{butler_id}({butler_name})]", event]
    if extra:
        parts.append(extra)
    if session_name:
        parts.append(f"session={session_name}")
    return " ".join(parts)


def fmt_transfer(
    from_agent: str,
    to_agent: str,
    reason: str = "",
    *,
    transfer_type: str = "",
    session_name: str = "",
) -> str:
    """构建发言权转移日志格式。

    Format: [SpeakerTransfer] from→to type reason
    """
    parts = [f"[SpeakerTransfer] {from_agent}→{to_agent}"]
    if transfer_type:
        parts.append(f"type={transfer_type}")
    if reason:
        parts.append(reason)
    if session_name:
        parts.append(f"session={session_name}")
    return " ".join(parts)


def fmt_interjection(
    agent_id: str,
    decision: str,
    *,
    display_name: str = "",
    extra: str = "",
) -> str:
    """构建插话日志格式。

    Format: [Interjection:agent] decision detail
    """
    ident = f"agent={agent_id}"
    if display_name:
        ident = f"agent={agent_id}({display_name})"
    parts = [f"[Interjection:{ident}]", decision]
    if extra:
        parts.append(extra)
    return " ".join(parts)
