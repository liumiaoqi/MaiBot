"""主动对话综合决策器。

综合情绪+时间+关系+上下文计算 proactive_score。
决策延迟 <100ms。
禁止在纯潜水群（30天无互动）中发起主动对话。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ProactiveDecision:
    """主动对话决策结果。"""

    should_trigger: bool = False
    proactive_score: float = 0.0
    reason: str = ""


class ProactiveDecisionMaker:
    """主动对话综合决策器。"""

    MIN_SCORE_FOR_TRIGGER = 0.5
    DORMANT_GROUP_DAYS = 30

    def evaluate(
        self,
        emotion_state: dict[str, int] | None = None,
        active_coefficient: float = 0.8,
        relationship_score: float = 0.0,
        last_interaction_days_ago: float | None = None,
        trigger_threshold: float = 0.5,
    ) -> ProactiveDecision:
        """综合评估是否应该触发主动对话。

        Args:
            emotion_state: 当前情绪状态。
            active_coefficient: 当前时段活跃系数。
            relationship_score: 关系分数（0-1000）。
            last_interaction_days_ago: 距上次互动的天数，None表示无互动。
            trigger_threshold: 触发阈值。

        Returns:
            ProactiveDecision: 决策结果。
        """
        start = time.perf_counter()

        if last_interaction_days_ago is not None and last_interaction_days_ago > self.DORMANT_GROUP_DAYS:
            return ProactiveDecision(
                should_trigger=False,
                proactive_score=0.0,
                reason=f"潜水群（{last_interaction_days_ago:.0f}天无互动）",
            )

        emotion_score = self._compute_emotion_score(emotion_state)
        time_score = active_coefficient
        relationship_score_norm = min(relationship_score / 1000.0, 1.0)

        proactive_score = (
            emotion_score * 0.4
            + time_score * 0.3
            + relationship_score_norm * 0.3
        )

        should_trigger = proactive_score >= max(trigger_threshold, self.MIN_SCORE_FOR_TRIGGER)

        reason_parts = []
        if emotion_score > 0.6:
            reason_parts.append("情绪驱动")
        if time_score > 0.7:
            reason_parts.append("时段活跃")
        if relationship_score_norm > 0.5:
            reason_parts.append("关系亲密")

        reason = "、".join(reason_parts) if reason_parts else "综合评分不足"

        elapsed_ms = (time.perf_counter() - start) * 1000
        if elapsed_ms > 100:
            logger.warning("主动对话决策耗时 %.1fms (目标<100ms)", elapsed_ms)

        return ProactiveDecision(
            should_trigger=should_trigger,
            proactive_score=round(proactive_score, 4),
            reason=reason,
        )

    def _compute_emotion_score(self, emotion_state: dict[str, int] | None) -> float:
        """从情绪状态计算情绪驱动分数。

        孤独、开心、兴奋维度较高时提升分数。
        """
        if not emotion_state:
            return 0.3

        positive_weights = {
            "happy": 0.3,
            "excited": 0.3,
            "lonely": 0.4,
            "sad": -0.1,
            "anxious": -0.2,
            "angry": -0.3,
            "calm": 0.1,
        }

        score = 0.0
        for emotion, intensity in emotion_state.items():
            weight = positive_weights.get(emotion, 0.0)
            score += weight * (intensity / 100.0)

        return max(0.0, min(1.0, score + 0.3))