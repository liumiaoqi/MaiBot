"""状态感知规则引擎——基于共居智能体状态调整行为参数。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from src.common.logger import get_logger
from src.maisaka.agent_autonomy.state_awareness.visibility_rule import StateVisibilityRule

if TYPE_CHECKING:
    from src.maisaka.agent_autonomy.vitality_manager import VitalityManager

logger = get_logger("agent_autonomy.rule_engine")

_COMPANION_VITALITY_THRESHOLD_ADJUSTMENT = 5.0
_COMPANION_VITALITY_TRIGGER_THRESHOLD = 60.0
_COMPANION_EMOTION_INFECTION_BONUS = 2.0
_COMPANION_EMOTION_INFECTION_TRIGGER = 80.0
_COMPANION_SAD_RESPONSE_THRESHOLD_ADJUSTMENT = 5.0
_COMPANION_SAD_TRIGGER_THRESHOLD = 50.0
_COMPANION_MENTION_VITALITY_BONUS = 5.0


@dataclass
class RuleEvaluationResult:
    """感知规则评估结果。"""

    intent_threshold_adjustment: float = 0.0
    infection_bonus: float = 0.0
    mention_bonus: float = 0.0
    triggered_rules: list[str] = field(default_factory=list)


class StateAwareRuleEngine:
    """状态感知规则引擎——纯规则计算，不调用 LLM。"""

    def __init__(
        self,
        vitality_manager: VitalityManager,
        visibility_rule: StateVisibilityRule,
    ) -> None:
        self._vitality_manager = vitality_manager
        self._visibility_rule = visibility_rule

    def evaluate_for_interjection(self, session_id: str) -> RuleEvaluationResult:
        """评估插话相关的感知规则（规则1+规则3）。"""
        result = RuleEvaluationResult()

        # 规则1：同伴生命力影响
        standby_agents = self._vitality_manager.get_standby_agents(session_id)
        high_vitality_count = sum(
            1 for info in standby_agents
            if info.vitality_value >= _COMPANION_VITALITY_TRIGGER_THRESHOLD
        )
        if high_vitality_count > 0:
            result.intent_threshold_adjustment += _COMPANION_VITALITY_THRESHOLD_ADJUSTMENT
            result.triggered_rules.append("companion_vitality_influence")

        # 规则3：同伴低落响应
        from src.maisaka.agent_autonomy.orchestrator import AgentOrchestrator
        orch = AgentOrchestrator.get_by_session(session_id)
        if orch is not None:
            for agent in orch.get_active_agents():
                if agent.emotion_manager is not None:
                    state = agent.emotion_manager.state
                    if state.dominant_emotion in ("sad", "lonely"):
                        if state.get_dominant_intensity() >= _COMPANION_SAD_TRIGGER_THRESHOLD:
                            result.intent_threshold_adjustment -= _COMPANION_SAD_RESPONSE_THRESHOLD_ADJUSTMENT
                            result.triggered_rules.append("companion_sad_response")
                            break

        return result

    def evaluate_for_infection(
        self, session_id: str, speaker_emotion_intensity: float
    ) -> float:
        """评估情绪感染增强规则（规则2）。"""
        if speaker_emotion_intensity >= _COMPANION_EMOTION_INFECTION_TRIGGER:
            return _COMPANION_EMOTION_INFECTION_BONUS
        return 0.0

    def evaluate_for_mention(self, session_id: str, mention_source_type: str) -> float:
        """评估同伴提及加成规则（规则4）。"""
        if mention_source_type == "agent":
            return _COMPANION_MENTION_VITALITY_BONUS
        return 0.0
