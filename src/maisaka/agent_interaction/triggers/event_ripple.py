"""事件涟漪触发器。

当智能体与用户发生重要交互（关系升级、情绪剧烈变化等）时，
向关联智能体传播信号。此触发器需要外部事件信号驱动。
"""

from __future__ import annotations

from typing import Any

from src.maisaka.agent.emotion import EmotionState
from src.maisaka.agent_interaction.models import AgentInteractionRelationshipRead
from src.maisaka.agent_interaction.trigger_base import BaseTrigger, TriggerEvaluation

# 涟漪传播的关系类型
_RIPPLE_PROPAGATION_TYPES = {"family", "romantic"}
_PROBABILITY_FACTOR = 0.5


class EventRippleTrigger(BaseTrigger):
    """事件涟漪触发器。

    触发逻辑：
    1. 外部事件信号驱动（如关系升级、情绪剧烈变化）
    2. 遍历该智能体 internal_relationships 中 family/romantic 关系的智能体
    3. 触发概率 = 事件影响强度 × mention_tendency × 0.5

    注意：此触发器的 evaluate 方法需要通过 metadata 传入
    event_impact（事件影响强度 0.0-1.0）和 event_desc（事件描述）。
    """

    async def evaluate(
        self,
        agent_id: str,
        emotion_state: EmotionState,
        relationships: list[AgentInteractionRelationshipRead],
        memory_context: dict[str, Any] | None = None,
        time_context: dict[str, Any] | None = None,
    ) -> TriggerEvaluation:
        event_impact = 0.0
        event_desc = ""

        if memory_context:
            event_impact = memory_context.get("event_impact", 0.0)
            event_desc = memory_context.get("event_desc", "重要交互")

        if event_impact <= 0.0:
            return TriggerEvaluation(initiator_agent_id=agent_id, interaction_type="event_ripple")

        best_target = ""
        best_prob = 0.0
        best_rel_type = ""

        for rel in relationships:
            if rel.relationship_type not in _RIPPLE_PROPAGATION_TYPES:
                continue

            mention = min(rel.score / 300.0, 1.0) if rel.score > 0 else 0.1
            prob = event_impact * mention * _PROBABILITY_FACTOR

            if prob > best_prob:
                best_prob = prob
                best_target = rel.target_agent_id
                best_rel_type = rel.relationship_type

        if not best_target:
            return TriggerEvaluation(initiator_agent_id=agent_id, interaction_type="event_ripple")

        reason = f"事件涟漪：{agent_id}与用户发生{event_desc}，向{best_target}传播信号"

        return TriggerEvaluation(
            should_trigger=True,
            trigger_probability=best_prob,
            initiator_agent_id=agent_id,
            target_agent_id=best_target,
            interaction_type="event_ripple",
            trigger_reason=reason,
            metadata={
                "event_impact": event_impact,
                "event_desc": event_desc,
                "relationship_type": best_rel_type,
            },
        )