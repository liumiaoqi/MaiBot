"""发言归属判定 — 纯函数，无 IO、无日志、不抛异常。

「自己」的唯一定义：`sender_type == "agent"` 且 `sender_agent_id == viewer_agent_id`。
禁止用昵称或正文前缀判定。
"""

from dataclasses import dataclass
from typing import Literal

from src.llm_models.payload_content.message import RoleType


__all__ = ["AttributionDecision", "SenderType", "decide_role"]


SenderType = Literal["user", "agent", "system"]


@dataclass(frozen=True, slots=True)
class AttributionDecision:
    """一次归属投影的决策结果。"""

    role: RoleType
    self_authored: bool
    degrade_reason: str


def decide_role(
    *,
    sender_type: str,
    sender_agent_id: str,
    viewer_agent_id: str,
    enabled: bool,
) -> AttributionDecision:
    """按结构化字段决定消息在请求体中的 role。

    降级原因：disabled / no_viewer / agent_without_id / system_sender / legacy_unknown。
    """
    if not enabled:
        return AttributionDecision(RoleType.User, False, "disabled")

    viewer = (viewer_agent_id or "").strip()
    if not viewer:
        return AttributionDecision(RoleType.User, False, "no_viewer")

    normalized_type = (sender_type or "").strip().lower()
    sender = (sender_agent_id or "").strip()

    if normalized_type == "agent":
        if not sender:
            return AttributionDecision(RoleType.User, False, "agent_without_id")
        if sender == viewer:
            return AttributionDecision(RoleType.Assistant, True, "")
        return AttributionDecision(RoleType.User, False, "")

    if normalized_type == "user":
        return AttributionDecision(RoleType.User, False, "")

    if normalized_type == "system":
        return AttributionDecision(RoleType.User, False, "system_sender")

    return AttributionDecision(RoleType.User, False, "legacy_unknown")