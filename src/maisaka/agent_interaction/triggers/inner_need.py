"""内部需求触发器。

当智能体情绪状态连续一段时间为 calm 且强度很低时，
产生"无聊"内部需求，主动寻求与其他智能体交互。
"""

from __future__ import annotations

from typing import Any

from src.maisaka.agent.emotion import EmotionState
from src.maisaka.agent_interaction.models import AgentInteractionRelationshipRead
from src.maisaka.agent_interaction.trigger_base import BaseTrigger, TriggerEvaluation

_CALM_INTENSITY_THRESHOLD = 20
_IDLE_DURATION_HOURS = 2.0
_PROBABILITY_FACTOR = 0.4


class InnerNeedTrigger(BaseTrigger):
    """内部需求触发器。

    触发逻辑：
    1. 智能体主导情绪为 calm 且强度 < 20
    2. 连续空闲时间 ≥ 2小时（通过 metadata 传入 idle_hours）
    3. 触发概率 = (1 - calm_intensity/20) × mention_tendency × 0.4
    4. 选择触发概率最高的目标智能体

    注意：空闲时长需要通过 metadata 中的 idle_hours 传入，
    如果未传入则默认使用情绪强度直接判断。
    """

    async def evaluate(
        self,
        agent_id: str,
        emotion_state: EmotionState,
        relationships: list[AgentInteractionRelationshipRead],
        memory_context: dict[str, Any] | None = None,
        time_context: dict[str, Any] | None = None,
    ) -> TriggerEvaluation:
        dominant = emotion_state.dominant_emotion
        intensity = emotion_state.get_dominant_intensity()

        if dominant != "calm" or intensity >= _CALM_INTENSITY_THRESHOLD:
            return TriggerEvaluation(initiator_agent_id=agent_id, interaction_type="inner_need")

        idle_hours = 0.0
        if memory_context:
            idle_hours = memory_context.get("idle_hours", 0.0)

        if idle_hours < _IDLE_DURATION_HOURS:
            return TriggerEvaluation(initiator_agent_id=agent_id, interaction_type="inner_need")

        best_target = ""
        best_prob = 0.0
        best_rel_type = ""

        for rel in relationships:
            mention = min(rel.score / 300.0, 1.0) if rel.score > 0 else 0.1
            prob = (1.0 - intensity / _CALM_INTENSITY_THRESHOLD) * mention * _PROBABILITY_FACTOR

            if prob > best_prob:
                best_prob = prob
                best_target = rel.target_agent_id
                best_rel_type = rel.relationship_type

        if not best_target:
            return TriggerEvaluation(initiator_agent_id=agent_id, interaction_type="inner_need")

        need_desc = "无聊"
        interaction_desc = "互动"
        reason = f"内部需求：{agent_id}感到{need_desc}，向{best_target}寻求{interaction_desc}"

        return TriggerEvaluation(
            should_trigger=True,
            trigger_probability=best_prob,
            initiator_agent_id=agent_id,
            target_agent_id=best_target,
            interaction_type="inner_need",
            trigger_reason=reason,
            metadata={
                "calm_intensity": intensity,
                "idle_hours": idle_hours,
                "relationship_type": best_rel_type,
            },
        )