"""内在需求引擎——智能体基于情绪、记忆、性格产生内在驱动力。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from src.common.logger import get_logger
from src.maisaka.agent_autonomy.autonomy_logger import AutonomyEventType, AutonomyLogger

logger = get_logger("agent_autonomy.inner_need")


@dataclass
class InnerNeed:
    """内在需求。"""

    need_type: str
    strength: float = 0.0
    source: str = ""
    description: str = ""

    def is_valid(self) -> bool:
        return self.strength > 0 and bool(self.description)


class BaseNeedCalculator(ABC):
    """内在需求计算器基类。"""

    @abstractmethod
    async def calculate(
        self,
        agent_id: str,
        emotion_state: Any | None = None,
        memory_context: dict[str, Any] | None = None,
        time_context: dict[str, Any] | None = None,
    ) -> list[InnerNeed]:
        """计算内在需求。"""
        ...


class EmotionNeedCalculator(BaseNeedCalculator):
    """基于情绪状态计算内在需求。"""

    async def calculate(
        self,
        agent_id: str,
        emotion_state: Any | None = None,
        memory_context: dict[str, Any] | None = None,
        time_context: dict[str, Any] | None = None,
    ) -> list[InnerNeed]:
        needs: list[InnerNeed] = []
        if emotion_state is None:
            return needs

        dominant = emotion_state.dominant_emotion
        intensity = emotion_state.get_dominant_intensity()

        if dominant == "lonely" and intensity >= 40:
            needs.append(InnerNeed(
                need_type="companionship",
                strength=min(intensity * 1.2, 100.0),
                source="emotion_driven",
                description="孤独时需要陪伴",
            ))

        if dominant == "excited" and intensity >= 50:
            needs.append(InnerNeed(
                need_type="sharing",
                strength=min(intensity * 1.0, 100.0),
                source="emotion_driven",
                description="兴奋时想分享",
            ))

        if dominant == "sad" and intensity >= 40:
            needs.append(InnerNeed(
                need_type="comfort",
                strength=min(intensity * 0.8, 100.0),
                source="emotion_driven",
                description="难过时需要安慰",
            ))

        if dominant == "calm" and intensity < 20:
            import time
            needs.append(InnerNeed(
                need_type="boredom",
                strength=30.0,
                source="emotion_driven",
                description="无聊时想找人说话",
            ))

        if dominant == "angry" and intensity >= 50:
            needs.append(InnerNeed(
                need_type="venting",
                strength=min(intensity * 0.6, 100.0),
                source="emotion_driven",
                description="生气时想发泄",
            ))

        if dominant == "anxious" and intensity >= 40:
            needs.append(InnerNeed(
                need_type="reassurance",
                strength=min(intensity * 0.7, 100.0),
                source="emotion_driven",
                description="焦虑时需要安心",
            ))

        return needs


class MemoryNeedCalculator(BaseNeedCalculator):
    """基于交互记忆计算内在需求。"""

    async def calculate(
        self,
        agent_id: str,
        emotion_state: Any | None = None,
        memory_context: dict[str, Any] | None = None,
        time_context: dict[str, Any] | None = None,
    ) -> list[InnerNeed]:
        needs: list[InnerNeed] = []
        if memory_context is None:
            return needs

        for target_id, profile_data in memory_context.items():
            if not isinstance(profile_data, dict):
                continue

            last_interaction = profile_data.get("last_interaction_at")
            if last_interaction is not None:
                import time
                try:
                    elapsed_hours = (time.time() - float(last_interaction)) / 3600
                    if elapsed_hours >= 24:
                        needs.append(InnerNeed(
                            need_type="missing",
                            strength=min(40.0 + elapsed_hours * 0.5, 80.0),
                            source="memory_driven",
                            description=f"想念{target_id}（{elapsed_hours:.0f}小时未交互）",
                        ))
                except (TypeError, ValueError):
                    pass

        return needs


class TimeNeedCalculator(BaseNeedCalculator):
    """基于时间画像计算内在需求。"""

    async def calculate(
        self,
        agent_id: str,
        emotion_state: Any | None = None,
        memory_context: dict[str, Any] | None = None,
        time_context: dict[str, Any] | None = None,
    ) -> list[InnerNeed]:
        needs: list[InnerNeed] = []
        if time_context is None:
            return needs

        hour = time_context.get("hour", -1)
        is_night_active = time_context.get("night_active", False)

        if 23 <= hour or hour < 5:
            if is_night_active:
                needs.append(InnerNeed(
                    need_type="night_chat",
                    strength=35.0,
                    source="time_driven",
                    description="深夜夜猫子，想找人聊天",
                ))

        return needs


class InnerNeedEngine:
    """内在需求引擎。"""

    def __init__(self) -> None:
        self._calculators: dict[str, BaseNeedCalculator] = {}
        self._autonomy_logger = AutonomyLogger.get()

    def register_calculator(self, need_type: str, calculator: BaseNeedCalculator) -> None:
        """注册内在需求计算器。"""
        self._calculators[need_type] = calculator

    async def evaluate(
        self,
        agent_id: str,
        emotion_state: Any | None = None,
        memory_context: dict[str, Any] | None = None,
        time_context: dict[str, Any] | None = None,
    ) -> list[InnerNeed]:
        """评估当前内在需求。"""
        all_needs: list[InnerNeed] = []

        for need_type, calculator in self._calculators.items():
            try:
                needs = await calculator.calculate(
                    agent_id=agent_id,
                    emotion_state=emotion_state,
                    memory_context=memory_context,
                    time_context=time_context,
                )
                all_needs.extend(needs)
            except Exception as exc:
                logger.warning(
                    f"[agent_autonomy] 内在需求计算异常: "
                    f"type={need_type} agent={agent_id} error={exc}"
                )

        valid_needs = [n for n in all_needs if n.is_valid()]
        valid_needs.sort(key=lambda n: n.strength, reverse=True)

        if valid_needs:
            need_summary = ", ".join(
                f"{n.need_type}({n.strength:.0f})" for n in valid_needs[:3]
            )
            self._autonomy_logger.log(
                agent_id,
                AutonomyEventType.INNER_NEED,
                f"评估结果: {need_summary}",
                level="debug",
            )

        return valid_needs