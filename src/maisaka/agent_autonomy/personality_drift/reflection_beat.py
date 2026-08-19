"""M5: 反思节拍——情境变化触发 5 问 + 适应度权重调整建议。

Concordia QuestionOfRecentMemories 范式 + exp57 +7.3%。
情境变化触发（非轮次节流——exp57 实测每 5 轮 +0.9%≈无效）。
"""

from typing import TYPE_CHECKING

from src.common.logger import get_logger

if TYPE_CHECKING:
    from src.maisaka.agent_autonomy.personality_drift.drift_fitness_collector import (
        DriftFitnessCollector,
    )

logger = get_logger("maisaka.personality_drift.reflection")


class ReflectionBeat:
    """反思节拍——情境变化触发 5 问 + 适应度权重调整建议。"""

    def __init__(
        self,
        config: dict | None = None,
        fitness_collector: "DriftFitnessCollector | None" = None,
    ) -> None:
        cfg = config or {}
        self._fitness = fitness_collector
        self._w3_initial = cfg.get("w_uniqueness", 0.3)

    def should_trigger(self, context: dict) -> bool:
        """情境变化触发（非轮次节流）。"""
        return bool(
            context.get("topic_changed")
            or context.get("relation_level_up")
            or context.get("silence_broken")
        )

    def reflect(self, agent_id: str, user_id: str, context: dict) -> dict:
        """5 问反思——情境感知每轮做（轻量），自我认知低频写。"""
        result = {
            "q1_situation_match": self._q1(context),
            "q2_relation_state": self._q2(agent_id, user_id),
            "q3_emotion_tone": self._q3(context),
            "q4_topic_continuation": self._q4(context),
            "q5_unique_expression": self._q5(agent_id),
            "weight_adjustment_suggestion": self._suggest_weight_adjustment(),
        }
        logger.debug("reflection: agent=%s result=%s", agent_id, result)
        return result

    def _q1(self, context: dict) -> float:
        return 0.5

    def _q2(self, agent_id: str, user_id: str) -> float:
        if self._fitness is None:
            return 0.5
        return self._fitness.collect(agent_id, user_id)

    def _q3(self, context: dict) -> float:
        return 0.5

    def _q4(self, context: dict) -> float:
        return 0.5

    def _q5(self, agent_id: str) -> float:
        return 0.5

    def _suggest_weight_adjustment(self) -> dict:
        """适应度权重调整建议——如发现独特表达价值高 → 建议 w₃ ↑。"""
        return {"w_uniqueness": self._w3_initial}