from dataclasses import dataclass
from typing import Any

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
    expression_layer_text: str = ""
    experience_layer_text: str = ""
    lambda_value: float = 0.5


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
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, '情绪管理器初始化失败', exception=exc)
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
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, '欲望引擎初始化失败', exception=exc)
            logger.warning("欲望引擎初始化失败: agent=%s error=%s", self._agent_id, exc)

    def _init_voice_generator(self) -> None:
        try:
            self._voice_generator = InnerVoiceGenerator(
                inner_voices=self._agent_config.inner_voices,
                template_text=self._agent_config.inner_voice_template_text,
            )
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, '内心声音生成器初始化失败', exception=exc)
            logger.warning("内心声音生成器初始化失败: agent=%s error=%s", self._agent_id, exc)

    async def get_state_snapshot(self) -> InnerWorldSnapshot:
        """获取内心世界完整状态快照。"""
        emotion_text = ""
        desire_summary = ""
        inner_voice = ""
        expression_text = ""
        experience_text = ""
        lambda_val = 0.5

        if self._emotion_manager is not None:
            try:
                emotion_text = self._emotion_manager.state.to_prompt_text()
            except Exception as exc:
                from src.core.error_escalation.types import ErrorLevel
                from src.core.error_escalation_port_registry import get_error_escalation_port
                port = get_error_escalation_port()
                if port is not None:
                    port.report(ErrorLevel.WARNING, '读取情绪文本失败，使用默认文本', exception=exc)
                logger.warning("操作异常 in inner_world.py", exc_info=True)
                emotion_text = "心情平静"

        if self._inner_need_engine is not None:
            try:
                needs = await self._inner_need_engine.evaluate(
                    agent_id=self._agent_id,
                    emotion_state=self._emotion_manager.state if self._emotion_manager else None,
                    time_context=None,
                )
                if needs:
                    desire_summary = "、".join(
                        f"{n.description}" for n in needs[:3] if n.description
                    )
            except Exception as exc:
                from src.core.error_escalation.types import ErrorLevel
                from src.core.error_escalation_port_registry import get_error_escalation_port
                port = get_error_escalation_port()
                if port is not None:
                    port.report(ErrorLevel.WARNING, '读取欲望摘要失败，使用空摘要', exception=exc)
                logger.warning("操作异常 in inner_world.py", exc_info=True)
                desire_summary = ""

        # T5.3: 分层性格 — 从 LayeredPersonality 获取 expression/experience 文本
        layered = self._agent_config.layered_personality
        if layered is not None:
            expression_text = layered.expression_layer or ""
            experience_text = layered.experience_layer or ""

        # T5.3: A3 λ 计算 — lazy import
        emotion_intensity = 0.0
        coactivation_strength = 0.0
        if self._emotion_manager is not None:
            try:
                state = self._emotion_manager.state
                dominant = getattr(state, "dominant_emotion", "calm")
                emotions = getattr(state, "emotions", {})
                if isinstance(emotions, dict) and dominant in emotions:
                    emotion_intensity = float(emotions[dominant]) / 100.0
            except Exception as exc:
                from src.core.error_escalation.types import ErrorLevel
                from src.core.error_escalation_port_registry import get_error_escalation_port
                port = get_error_escalation_port()
                if port is not None:
                    port.report(ErrorLevel.WARNING, '读取情绪强度失败，使用默认值', exception=exc)
                logger.warning(f"读取情绪强度失败，使用默认值: {exc}")
                emotion_intensity = 0.0

        # 共激活强度：从内部关系中估算
        if self._agent_config.internal_relationships:
            coactivation_strength = min(1.0, len(self._agent_config.internal_relationships) * 0.15)

        try:
            from src.maisaka.agent_autonomy.personality_algo.engine import PersonalityAlgorithmEngine
            engine = PersonalityAlgorithmEngine(self._agent_config.layered_personality_config)
            lambda_val = engine.compute_lambda(emotion_intensity, coactivation_strength)
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, '计算 λ 失败，使用默认值', exception=exc)
            logger.warning(f"计算 λ 失败，使用默认值: {exc}")
            lambda_val = 0.5

        # T5.3: 可选 LLM 路径 — 如果 LLM 服务可用则用 generate_llm
        if self._voice_generator is not None:
            try:
                from src.core.adapters.llm_service_port import get_llm_service
                llm_svc = get_llm_service()
                inner_voice = await self._voice_generator.generate_llm(
                    experience_layer_text=experience_text,
                    emotion_state=self._emotion_manager.state if self._emotion_manager else None,
                    desire_summary=desire_summary,
                    memory_personality=self._memory_personality,
                    current_context="",
                    prev_thought_summary="",
                    relationship_summary="",
                    inner_speech_style=self._agent_config.inner_speech_style,
                    llm_service=llm_svc,
                    timeout_seconds=2.0,
                    max_output_tokens=500,
                )
            except Exception as exc:
                from src.core.error_escalation.types import ErrorLevel
                from src.core.error_escalation_port_registry import get_error_escalation_port
                port = get_error_escalation_port()
                if port is not None:
                    port.report(ErrorLevel.WARNING, 'LLM 内言语生成失败，回退到规则引擎', exception=exc)
                logger.warning("LLM 内言语生成失败，回退到规则引擎: %s", exc)
                try:
                    inner_voice = self._voice_generator.generate(
                        emotion_state=self._emotion_manager.state if self._emotion_manager else None,
                        desire_summary=desire_summary,
                        memory_personality=self._memory_personality,
                    )
                except Exception as exc2:
                    from src.core.error_escalation.types import ErrorLevel
                    from src.core.error_escalation_port_registry import get_error_escalation_port
                    port = get_error_escalation_port()
                    if port is not None:
                        port.report(ErrorLevel.WARNING, '规则引擎生成内心声音失败，使用默认文本', exception=exc2)
                    logger.warning("操作异常 in inner_world.py", exc_info=True)
                    inner_voice = "心里闪过一个念头..."

        return InnerWorldSnapshot(
            emotion_state_text=emotion_text,
            desire_summary=desire_summary,
            inner_voice_text=inner_voice,
            memory_personality_params=self._memory_personality,
            expression_layer_text=expression_text,
            experience_layer_text=experience_text,
            lambda_value=lambda_val,
        )

    async def generate_inner_voice(self) -> str:
        """纯规则生成内心声音文本。"""
        desire_summary = ""
        if self._inner_need_engine is not None:
            try:
                needs = await self._inner_need_engine.evaluate(
                    agent_id=self._agent_id,
                    emotion_state=self._emotion_manager.state if self._emotion_manager else None,
                    time_context=None,
                )
                if needs:
                    desire_summary = "、".join(
                        f"{n.description}" for n in needs[:3] if n.description
                    )
            except Exception as exc:
                from src.core.error_escalation.types import ErrorLevel
                from src.core.error_escalation_port_registry import get_error_escalation_port
                port = get_error_escalation_port()
                if port is not None:
                    port.report(ErrorLevel.WARNING, '规则引擎生成内心声音失败，使用空摘要', exception=exc)
                logger.warning("操作异常 in inner_world.py", exc_info=True)
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
                from src.core.error_escalation.types import ErrorLevel
                from src.core.error_escalation_port_registry import get_error_escalation_port
                port = get_error_escalation_port()
                if port is not None:
                    port.report(ErrorLevel.WARNING, '情绪更新失败', exception=exc)
                logger.warning("情绪更新失败: agent=%s error=%s", self._agent_id, exc)

    async def update_on_tick(self, time_context: dict[str, Any] | None = None) -> None:
        """心跳时触发情绪衰减和欲望评估。"""
        if self._emotion_manager is not None:
            try:
                self._emotion_manager.apply_decay()
            except Exception as exc:
                from src.core.error_escalation.types import ErrorLevel
                from src.core.error_escalation_port_registry import get_error_escalation_port
                port = get_error_escalation_port()
                if port is not None:
                    port.report(ErrorLevel.WARNING, '情绪衰减跳过', exception=exc)
                logger.warning("情绪衰减跳过: agent=%s error=%s", self._agent_id, exc)

    @property
    def emotion_manager(self) -> Any | None:
        return self._emotion_manager

    @property
    def inner_need_engine(self) -> Any | None:
        return self._inner_need_engine

    @property
    def memory_personality(self) -> MemoryPersonalityV2:
        return self._memory_personality
