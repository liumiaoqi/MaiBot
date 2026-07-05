"""情绪驱动触发器。

当智能体情绪强度超过阈值时，根据情绪类型和关系亲密度
选择最合适的目标智能体发起交互。
"""

from __future__ import annotations

from typing import Any

from src.maisaka.agent.emotion import EmotionState
from src.maisaka.agent_interaction.models import AgentInteractionRelationshipRead
from src.maisaka.agent_interaction.trigger_base import BaseTrigger, TriggerEvaluation

# 情绪-关系匹配系数：{情绪类型: {关系类型: 系数}}
_EMOTION_RELATIONSHIP_COEFFICIENT: dict[str, dict[str, float]] = {
    "lonely": {"family": 1.5, "romantic": 1.5, "friend": 1.0, "mentor": 0.8, "rival": 0.3},
    "happy": {"friend": 1.2, "family": 1.0, "romantic": 1.0, "mentor": 0.6, "rival": 0.5},
    "excited": {"friend": 1.0, "rival": 1.0, "family": 0.8, "romantic": 0.8, "mentor": 0.5},
    "anxious": {"family": 1.3, "mentor": 1.3, "romantic": 1.0, "friend": 0.8, "rival": 0.2},
    "sad": {"family": 1.3, "romantic": 1.2, "friend": 1.0, "mentor": 0.8, "rival": 0.2},
    "angry": {"rival": 1.2, "family": 0.8, "friend": 0.6, "romantic": 0.5, "mentor": 0.3},
    "calm": {"friend": 0.6, "family": 0.5, "mentor": 0.5, "romantic": 0.5, "rival": 0.3},
}

_DEFAULT_COEFFICIENT = 0.5

# 情绪驱动的交互描述映射
_INTERACTION_DESC: dict[str, str] = {
    "lonely": "寻求陪伴",
    "happy": "分享喜悦",
    "excited": "分享兴奋",
    "anxious": "寻求安慰",
    "sad": "寻求慰藉",
    "angry": "表达不满",
    "calm": "闲聊",
}

_INTENSITY_THRESHOLD = 60
_PROBABILITY_THRESHOLD = 0.3


class EmotionDrivenTrigger(BaseTrigger):
    """情绪驱动触发器。

    触发逻辑：遍历智能体关系，对每个关系计算触发概率：
    主导情绪强度/100 × mention_tendency × 情绪-关系匹配系数。
    选择触发概率最高的目标智能体。
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

        if intensity < _INTENSITY_THRESHOLD:
            return TriggerEvaluation(initiator_agent_id=agent_id, interaction_type="emotion_driven")

        best_target = ""
        best_prob = 0.0
        best_rel_type = ""

        for rel in relationships:
            coeff_map = _EMOTION_RELATIONSHIP_COEFFICIENT.get(dominant, {})
            coeff = coeff_map.get(rel.relationship_type, _DEFAULT_COEFFICIENT)
            mention = min(rel.score / 300.0, 1.0) if rel.score > 0 else 0.1
            prob = (intensity / 100.0) * mention * coeff

            if prob > best_prob:
                best_prob = prob
                best_target = rel.target_agent_id
                best_rel_type = rel.relationship_type

        if best_prob < _PROBABILITY_THRESHOLD or not best_target:
            return TriggerEvaluation(initiator_agent_id=agent_id, interaction_type="emotion_driven")

        desc = _INTERACTION_DESC.get(dominant, "发起交互")
        reason = f"情绪驱动：{agent_id}的{dominant}强度{intensity:.0f}，向{best_target}发起{desc}"

        return TriggerEvaluation(
            should_trigger=True,
            trigger_probability=best_prob,
            initiator_agent_id=agent_id,
            target_agent_id=best_target,
            interaction_type="emotion_driven",
            trigger_reason=reason,
            metadata={
                "dominant_emotion": dominant,
                "intensity": intensity,
                "relationship_type": best_rel_type,
            },
        )