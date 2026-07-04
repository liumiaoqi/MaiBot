"""ProactiveEngine 主动对话引擎。

整合决策器+频率控制器+内容生成器。
与现有 enqueue_proactive_task() 兼容。
主动对话决策延迟 <3秒。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from src.maisaka.agent.config import AgentConfig
from src.maisaka.agent.emotion import EmotionManager

from .content import ProactiveContent, ProactiveContentGenerator
from .decision import ProactiveDecision, ProactiveDecisionMaker
from .frequency import ProactiveFrequencyController

logger = logging.getLogger(__name__)


@dataclass
class ProactiveResult:
    """主动对话引擎执行结果。"""

    should_trigger: bool = False
    proactive_score: float = 0.0
    content: Optional[ProactiveContent] = None
    reason: str = ""
    duration_ms: float = 0.0
    agent_id: str = ""


class ProactiveEngine:
    """ProactiveEngine 主动对话引擎。

    整合决策器+频率控制器+内容生成器，与现有 enqueue_proactive_task() 兼容。
    """

    def __init__(
        self,
        frequency_controller: ProactiveFrequencyController | None = None,
        decision_maker: ProactiveDecisionMaker | None = None,
        content_generator: ProactiveContentGenerator | None = None,
    ) -> None:
        self._frequency_controller = frequency_controller or ProactiveFrequencyController()
        self._decision_maker = decision_maker or ProactiveDecisionMaker()
        self._content_generator = content_generator or ProactiveContentGenerator()

    def evaluate(
        self,
        agent_config: AgentConfig,
        emotion_manager: EmotionManager | None = None,
        time_active_coefficient: float = 0.8,
        time_period_label: str = "",
        relationship_score: float = 0.0,
        last_interaction_days_ago: float | None = None,
    ) -> ProactiveResult:
        """评估并生成主动对话。

        Args:
            agent_config: 智能体配置。
            emotion_manager: 情绪管理器。
            time_active_coefficient: 当前时段活跃系数。
            time_period_label: 时段标签。
            relationship_score: 关系分数。
            last_interaction_days_ago: 距上次互动天数。

        Returns:
            ProactiveResult: 执行结果。
        """
        start = time.perf_counter()
        aid = agent_config.agent_id
        proactive_cfg = agent_config.proactive_config

        if not proactive_cfg.enabled:
            return ProactiveResult(
                should_trigger=False,
                reason="主动对话未启用",
                agent_id=aid,
            )

        if not self._frequency_controller.can_trigger(
            agent_id=aid,
            max_frequency_per_hour=proactive_cfg.max_frequency_per_hour,
            cooldown_seconds=proactive_cfg.cooldown_seconds,
        ):
            return ProactiveResult(
                should_trigger=False,
                reason="频率控制抑制",
                agent_id=aid,
            )

        emotion_state = None
        if emotion_manager is not None:
            try:
                state = emotion_manager.get_current_state()
                emotion_state = state.emotions
            except Exception:
                pass

        decision = self._decision_maker.evaluate(
            emotion_state=emotion_state,
            active_coefficient=time_active_coefficient,
            relationship_score=relationship_score,
            last_interaction_days_ago=last_interaction_days_ago,
            trigger_threshold=proactive_cfg.trigger_threshold,
        )

        if not decision.should_trigger:
            return ProactiveResult(
                should_trigger=False,
                proactive_score=decision.proactive_score,
                reason=decision.reason,
                agent_id=aid,
            )

        content = self._content_generator.generate(
            display_name=agent_config.display_name,
            personality=agent_config.personality,
            emotion_state=emotion_state,
            time_period_label=time_period_label,
        )

        self._frequency_controller.record_trigger(aid)

        elapsed_ms = (time.perf_counter() - start) * 1000
        if elapsed_ms > 3000:
            logger.warning("主动对话决策耗时 %.1fms (目标<3s)", elapsed_ms)

        logger.info(
            "主动对话触发: agent=%s score=%.3f reason=%s",
            aid,
            decision.proactive_score,
            decision.reason,
        )

        return ProactiveResult(
            should_trigger=True,
            proactive_score=decision.proactive_score,
            content=content,
            reason=decision.reason,
            duration_ms=elapsed_ms,
            agent_id=aid,
        )

    def build_proactive_intent(
        self,
        result: ProactiveResult,
    ) -> dict[str, Any] | None:
        """将主动对话结果转换为 enqueue_proactive_task() 兼容的参数。

        Args:
            result: 主动对话执行结果。

        Returns:
            兼容参数字典，或 None（不应触发时）。
        """
        if not result.should_trigger or result.content is None:
            return None

        return {
            "plugin_id": "maisaka_proactive",
            "intent": result.content.message,
            "reason": result.reason,
            "priority": "normal",
            "metadata": {
                "proactive_score": result.proactive_score,
                "emotion_tone": result.content.emotion_tone,
                "agent_id": result.agent_id,
            },
        }