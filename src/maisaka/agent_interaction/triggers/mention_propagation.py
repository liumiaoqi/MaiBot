"""提及传递触发器。

当智能体在对话中被自然提及时，被提及智能体产生"被提及反应"，
可能触发情绪和关系变化。此触发器需要外部信号驱动，不自行轮询。
"""

from __future__ import annotations

from typing import Any

from src.maisaka.agent.emotion import EmotionState
from src.maisaka.agent_interaction.models import AgentInteractionRelationshipRead
from src.maisaka.agent_interaction.trigger_base import BaseTrigger, TriggerEvaluation

_MENTION_TENDENCY_THRESHOLD = 0.3
_PROBABILITY_FACTOR = 0.6


class MentionPropagationTrigger(BaseTrigger):
    """提及传递触发器。

    触发逻辑：
    1. 外部信号驱动（由对话运行时调用）
    2. 检查被提及智能体与提及方的 mention_tendency
    3. mention_tendency ≥ 0.3 时触发概率 = mention_tendency × 0.6
    4. 被提及智能体产生"被提及反应"

    注意：此触发器的 evaluate 方法需要通过 metadata 传入
    mentioner_id（提及方智能体ID）和 mention_tendency 值。
    """

    async def evaluate(
        self,
        agent_id: str,
        emotion_state: EmotionState,
        relationships: list[AgentInteractionRelationshipRead],
        memory_context: dict[str, Any] | None = None,
        time_context: dict[str, Any] | None = None,
    ) -> TriggerEvaluation:
        mentioner_id = ""
        mention_tendency = 0.0

        if memory_context:
            mentioner_id = memory_context.get("mentioner_id", "")
            mention_tendency = memory_context.get("mention_tendency", 0.0)

        if not mentioner_id:
            for rel in relationships:
                if rel.target_agent_id == agent_id:
                    continue
                mention_tendency = min(rel.score / 300.0, 1.0) if rel.score > 0 else 0.0
                if mention_tendency >= _MENTION_TENDENCY_THRESHOLD:
                    mentioner_id = rel.target_agent_id
                    break

        if mention_tendency < _MENTION_TENDENCY_THRESHOLD or not mentioner_id:
            return TriggerEvaluation(initiator_agent_id=agent_id, interaction_type="mention_propagation")

        prob = mention_tendency * _PROBABILITY_FACTOR

        reason = f"提及传递：{agent_id}被{mentioner_id}提及，mention_tendency={mention_tendency:.2f}"

        return TriggerEvaluation(
            should_trigger=True,
            trigger_probability=prob,
            initiator_agent_id=agent_id,
            target_agent_id=mentioner_id,
            interaction_type="mention_propagation",
            trigger_reason=reason,
            metadata={
                "mentioner_id": mentioner_id,
                "mention_tendency": mention_tendency,
            },
        )