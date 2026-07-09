from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Optional

from src.common.logger import get_logger
from src.maisaka.agent.config import AgentConfig, MemoryPersonalityV2
from src.maisaka.agent_autonomy.inner_voice import InnerVoiceGenerator

logger = get_logger("agent_autonomy.inner_world")


@dataclass(frozen=True)
class InnerWorldSnapshot:
    """内心世界状态快照——不可变，供 ThinkContext 使用。"""
    emotion_state_text: str
    desire_summary: str
    inner_voice_text: str
    memory_personality_params: MemoryPersonalityV2


class InnerWorld:
    """内心世界门面——统一管理情绪/欲望/记忆性格三层。"""

    def __init__(
        self,
        agent_id: str,
        agent_config: AgentConfig,
        inner_need_engine: Any | None = None,
    ) -> None:
        self._agent_id = agent_id
        self._agent_config = agent_config
        self._memory_personality = agent_config.memory_personality

        self._emotion_manager: Any | None = None
        self._inner_need_engine: Any | None = inner_need_engine
        self._voice_generator: InnerVoiceGenerator | None = None

        self._init_emotion()
        if self._inner_need_engine is None:
            self._init_desire()
        self._init_voice_generator()

    def _init_emotion(self) -> None:
        try:
            from src.maisaka.agent_interaction.emotion_registry import AgentEmotionManagerRegistry

            registry = AgentEmotionManagerRegistry()
            self._emotion_manager = registry.get_emotion_manager(self._agent_id)
        except Exception as exc:
            logger.warning("情绪管理器初始化失败: agent=%s error=%s", self._agent_id, exc)

    def _init_desire(self) -> None:
        try:
            from src.maisaka.agent_autonomy.inner_need import InnerNeedEngine
            from src.maisaka.agent_autonomy.inner_need import (
                EmotionNeedCalculator,
                MemoryNeedCalculator,
                TimeNeedCalculator,
            )

            engine = InnerNeedEngine()
            engine.register_calculator("emotion_driven", EmotionNeedCalculator())
            engine.register_calculator("memory_driven", MemoryNeedCalculator())
            engine.register_calculator("time_driven", TimeNeedCalculator())
            self._inner_need_engine = engine
        except Exception as exc:
            logger.warning("欲望引擎初始化失败: agent=%s error=%s", self._agent_id, exc)

    def _init_voice_generator(self) -> None:
        try:
            self._voice_generator = InnerVoiceGenerator(
                inner_voices=self._agent_config.inner_voices,
                template_text=self._agent_config.inner_voice_template_text,
            )
        except Exception as exc:
            logger.warning("内心声音生成器初始化失败: agent=%s error=%s", self._agent_id, exc)

    def get_state_snapshot(self) -> InnerWorldSnapshot:
        """获取内心世界完整状态快照。"""
        emotion_text = ""
        desire_summary = ""
        inner_voice = ""

        if self._emotion_manager is not None:
            try:
                emotion_text = self._emotion_manager.state.to_prompt_text()
            except Exception:
                emotion_text = "心情平静"

        if self._inner_need_engine is not None:
            try:
                needs = self._inner_need_engine.evaluate(
                    agent_id=self._agent_id,
                    emotion_state=self._emotion_manager.state if self._emotion_manager else None,
                    time_context=None,
                )
                if needs:
                    desire_summary = "、".join(
                        f"{n.description}" for n in needs[:3] if n.description
                    )
            except Exception:
                desire_summary = ""

        if self._voice_generator is not None:
            try:
                inner_voice = self._voice_generator.generate(
                    emotion_state=self._emotion_manager.state if self._emotion_manager else None,
                    desire_summary=desire_summary,
                    memory_personality=self._memory_personality,
                )
            except Exception:
                inner_voice = "心里闪过一个念头..."

        return InnerWorldSnapshot(
            emotion_state_text=emotion_text,
            desire_summary=desire_summary,
            inner_voice_text=inner_voice,
            memory_personality_params=self._memory_personality,
        )

    def generate_inner_voice(self) -> str:
        """纯规则生成内心声音文本。"""
        desire_summary = ""
        if self._inner_need_engine is not None:
            try:
                needs = self._inner_need_engine.evaluate(
                    agent_id=self._agent_id,
                    emotion_state=self._emotion_manager.state if self._emotion_manager else None,
                    time_context=None,
                )
                if needs:
                    desire_summary = "、".join(
                        f"{n.description}" for n in needs[:3] if n.description
                    )
            except Exception:
                desire_summary = ""

        if self._voice_generator is None:
            return "心里闪过一个念头..."
        return self._voice_generator.generate(
            emotion_state=self._emotion_manager.state if self._emotion_manager else None,
            desire_summary=desire_summary,
            memory_personality=self._memory_personality,
        )

    def update_on_stimulus(self, stimulus_type: str, intensity: float) -> None:
        """刺激到达时更新情绪状态。"""
        if self._emotion_manager is not None:
            try:
                self._emotion_manager.apply_trigger(stimulus_type, intensity)
            except Exception as exc:
                logger.warning("情绪更新失败: agent=%s error=%s", self._agent_id, exc)

    async def update_on_tick(self, time_context: dict[str, Any] | None = None) -> None:
        """心跳时触发情绪衰减和欲望评估。"""
        if self._emotion_manager is not None:
            try:
                self._emotion_manager.apply_decay()
            except Exception as exc:
                logger.debug("情绪衰减跳过: agent=%s error=%s", self._agent_id, exc)

    @property
    def emotion_manager(self) -> Any | None:
        return self._emotion_manager

    @property
    def inner_need_engine(self) -> Any | None:
        return self._inner_need_engine

    @property
    def memory_personality(self) -> MemoryPersonalityV2:
        return self._memory_personality