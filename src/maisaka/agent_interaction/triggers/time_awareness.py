"""时间感知触发器。

根据当前时段和智能体的时间行为画像，在活跃时段
对亲密关系智能体发起交互。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from src.maisaka.agent.emotion import EmotionState
from src.maisaka.agent_interaction.models import AgentInteractionRelationshipRead
from src.maisaka.agent_interaction.trigger_base import BaseTrigger, TriggerEvaluation

# 深夜时段仅对亲密关系触发
_INTIMATE_TYPES = {"family", "romantic"}
_ACTIVE_COEFFICIENT_THRESHOLD = 0.8
_LATE_NIGHT_HOURS = range(22, 24)

# 时段→配置字段的映射
_PERIOD_FIELD_MAP: dict[str, str] = {
    "morning": "morning_active_coefficient",
    "forenoon": "morning_active_coefficient",
    "afternoon": "afternoon_active_coefficient",
    "evening": "evening_active_coefficient",
    "night": "evening_active_coefficient",
    "late_night": "night_active_coefficient",
}


class TimeAwarenessTrigger(BaseTrigger):
    """时间感知触发器。

    触发逻辑：
    1. 获取当前时段和智能体对应的活跃系数
    2. 活跃系数 ≥ 0.8 时，对亲密关系计算触发概率
    3. 深夜时段（22:00-06:00）仅对 family/romantic 关系触发
    4. 触发概率 = 活跃系数 × mention_tendency × 0.8
    """

    def __init__(self) -> None:
        self._time_service = None

    def _get_active_coefficient(self, time_context: dict[str, Any]) -> float:
        return time_context.get("active_coefficient", 0.5)

    def _get_time_period(self, time_context: dict[str, Any]) -> str:
        return time_context.get("time_period", "afternoon")

    def _is_late_night(self) -> bool:
        hour = datetime.now().hour
        return hour >= 22 or hour < 6

    async def evaluate(
        self,
        agent_id: str,
        emotion_state: EmotionState,
        relationships: list[AgentInteractionRelationshipRead],
        memory_context: dict[str, Any] | None = None,
        time_context: dict[str, Any] | None = None,
    ) -> TriggerEvaluation:
        if time_context is None:
            return TriggerEvaluation(initiator_agent_id=agent_id, interaction_type="time_awareness")

        active_coeff = self._get_active_coefficient(time_context)
        time_period = self._get_time_period(time_context)
        is_late_night = self._is_late_night()

        if active_coeff < _ACTIVE_COEFFICIENT_THRESHOLD:
            return TriggerEvaluation(initiator_agent_id=agent_id, interaction_type="time_awareness")

        best_target = ""
        best_prob = 0.0
        best_rel_type = ""

        for rel in relationships:
            if is_late_night and rel.relationship_type not in _INTIMATE_TYPES:
                continue

            mention = min(rel.score / 300.0, 1.0) if rel.score > 0 else 0.1
            prob = active_coeff * mention * 0.8

            if prob > best_prob:
                best_prob = prob
                best_target = rel.target_agent_id
                best_rel_type = rel.relationship_type

        if not best_target:
            return TriggerEvaluation(initiator_agent_id=agent_id, interaction_type="time_awareness")

        period_label = "深夜" if is_late_night else time_period
        reason = f"时间感知：{agent_id}在{period_label}的活跃系数{active_coeff:.1f}，向{best_target}发起互动"

        return TriggerEvaluation(
            should_trigger=True,
            trigger_probability=best_prob,
            initiator_agent_id=agent_id,
            target_agent_id=best_target,
            interaction_type="time_awareness",
            trigger_reason=reason,
            metadata={
                "time_period": time_period,
                "active_coefficient": active_coeff,
                "is_late_night": is_late_night,
                "relationship_type": best_rel_type,
            },
        )