import asyncio
import random
from typing import Optional

from src.common.logger import get_logger
from src.maisaka.agent.config import InnerVoiceConfig, InnerVoiceStyle, MemoryPersonalityV2

logger = get_logger("agent_autonomy.inner_voice")

_VALENCE_MAP = {"POSITIVE": 1, "NEGATIVE": -1, "NEUTRAL": 0}

_EMOTION_VALENCE = {
    "happy": 1, "excited": 1, "calm": 0,
    "sad": -1, "anxious": -1, "angry": -1, "lonely": -1,
}

_STYLE_FRAGMENTS = {
    InnerVoiceStyle.AMPLIFY: "{name}在蠢蠢欲动，{desc}",
    InnerVoiceStyle.NEUTRALIZE: "{name}冷静地审视，{desc}",
    InnerVoiceStyle.PRESERVE: "{name}默默感受，{desc}",
    InnerVoiceStyle.INVERT: "{name}偏偏不这么想，{desc}",
    InnerVoiceStyle.CHAOTIC: "{name}的念头乱窜，{desc}",
}

_EMOTION_DESC = {
    "happy": "心里暖洋洋的", "excited": "热血沸腾",
    "calm": "波澜不惊", "sad": "有些低落",
    "anxious": "隐隐不安", "angry": "一股火气",
    "lonely": "空落落的",
}

_NEED_DESC = {
    "emotion_driven": "想表达什么",
    "memory_driven": "想起了什么",
    "time_driven": "想做点什么",
}


class InnerVoiceGenerator:
    """内心声音生成器——纯规则引擎，不调用 LLM。"""

    def __init__(
        self,
        inner_voices: list[InnerVoiceConfig],
        template_text: str = "",
        fallback_text: str = "心里闪过一个念头...",
    ) -> None:
        self._inner_voices = inner_voices
        self._template_text = template_text
        self._fallback_text = fallback_text

    def generate(
        self,
        emotion_state: Optional[object] = None,
        desire_summary: str = "",
        memory_personality: Optional[MemoryPersonalityV2] = None,
        current_context: str = "",
        prev_thought_summary: str = "",
    ) -> str:
        if self._inner_voices:
            return self._generate_multi_voice(emotion_state, desire_summary, memory_personality, prev_thought_summary)
        if self._template_text:
            return self._render_template(emotion_state, desire_summary, current_context)
        return self._fallback_text

    async def generate_llm(
        self,
        experience_layer_text: str,
        emotion_state: object,
        desire_summary: str = "",
        memory_personality: object = None,
        current_context: str = "",
        prev_thought_summary: str = "",
        relationship_summary: str = "",
        inner_speech_style: object = None,
        llm_service: object = None,
        timeout_seconds: float = 2.0,
        max_output_tokens: int = 500,
    ) -> str:
        """L1 LLM 路径：用云端小模型生成 inner_voice。极短 prompt，不传完整对话历史。"""
        # 提取情绪文本
        emotion_text = ""
        if emotion_state is not None:
            dominant = getattr(emotion_state, "dominant_emotion", "")
            if dominant:
                emotion_text = _EMOTION_DESC.get(dominant, dominant)

        # 构建极短 prompt（≤ 200 tokens）
        prompt_parts: list[str] = []
        if experience_layer_text:
            prompt_parts.append(f"内心底色：{experience_layer_text}")
        if emotion_text:
            prompt_parts.append(f"当前情绪：{emotion_text}")
        if relationship_summary:
            prompt_parts.append(f"关系：{relationship_summary}")

        # 风格指令
        style_hint = "用一句话（不超过30字）表达此刻的内心独白，像内心声音，不要解释。"
        if inner_speech_style is not None:
            style_type = getattr(inner_speech_style, "style", "fragmented")
            if style_type == "fragmented":
                style_hint = "用碎片化的一句话（不超过20字）表达内心独白，跳跃、不完整，像真实的内心声音。"
            elif style_type == "narrative":
                style_hint = "用一句话（不超过40字）表达内心独白，叙事化但仍然是内心声音。"
        prompt_parts.append(style_hint)

        prompt = "。".join(prompt_parts)

        # 尝试 LLM 路径
        if llm_service is not None:
            try:
                from src.common.data_models.llm_service_data_models import LLMGenerationOptions

                options = LLMGenerationOptions(
                    temperature=0.9,
                    max_tokens=min(max_output_tokens, 128),
                )
                response = await asyncio.wait_for(
                    llm_service.generate_response(
                        task_name="utils",
                        capabilities=["text_generation", "tool_calling"],
                        prompt=prompt,
                        options=options,
                    ),
                    timeout=timeout_seconds,
                )
                if response and getattr(response, "content", ""):
                    content = response.content.strip()
                    if content:
                        return content[:200]
            except Exception as exc:
                # P1: 补 port.report 双通道上报
                from src.core.error_escalation.types import ErrorLevel
                from src.core.error_escalation_port_registry import get_error_escalation_port
                _port = get_error_escalation_port()
                if _port is not None:
                    _port.report(ErrorLevel.WARNING, "LLM 内言语生成失败，回退到规则引擎", exception=exc)
                logger.debug("LLM 内言语生成失败，回退到规则引擎")

        # 回退到纯规则路径
        return self.generate(
            emotion_state=emotion_state,
            desire_summary=desire_summary,
            memory_personality=memory_personality,
            current_context=current_context,
            prev_thought_summary=prev_thought_summary,
        )

    def _generate_multi_voice(
        self,
        emotion_state: Optional[object],
        desire_summary: str,
        memory_personality: Optional[MemoryPersonalityV2],
        prev_thought_summary: str = "",
    ) -> str:
        fragments: list[tuple[float, str]] = []

        dominant_emotion = "calm"
        dominant_intensity = 0.0
        if emotion_state is not None:
            dominant_emotion = getattr(emotion_state, "dominant_emotion", "calm")
            emotions = getattr(emotion_state, "emotions", {})
            dominant_intensity = emotions.get(dominant_emotion, 0.0) if isinstance(emotions, dict) else 0.0

        emotion_valence = _EMOTION_VALENCE.get(dominant_emotion, 0)

        for voice in self._inner_voices:
            voice_valence = _VALENCE_MAP.get(voice.valence_bias, 0)

            alignment = 1.0
            if emotion_valence != 0 and voice_valence != 0:
                alignment = 1.0 if emotion_valence * voice_valence > 0 else 0.3

            weight = voice.weight_multiplier * alignment

            if voice.concept_focus and memory_personality and memory_personality.attention_tags:
                overlap = set(voice.concept_focus) & set(memory_personality.attention_tags)
                if overlap:
                    weight *= 1.0 + 0.2 * len(overlap)

            # LS-0: prev_thought_summary 与 concept_focus 匹配时权重 bonus
            if prev_thought_summary and voice.concept_focus:
                for concept in voice.concept_focus:
                    if concept in prev_thought_summary:
                        weight += 0.3
                        break

            _ = self._apply_style(voice.style, dominant_intensity)
            emotion_desc = _EMOTION_DESC.get(dominant_emotion, "心有所感")

            if voice.style == InnerVoiceStyle.INVERT:
                if emotion_valence > 0:
                    emotion_desc = "哼，才不稀罕"
                elif emotion_valence < 0:
                    emotion_desc = "偏要笑出来"
                else:
                    emotion_desc = "偏要反着来"
            elif voice.style == InnerVoiceStyle.AMPLIFY:
                emotion_desc = f"{emotion_desc}，非常强烈"
            elif voice.style == InnerVoiceStyle.NEUTRALIZE:
                emotion_desc = "冷静下来想想"

            desc = emotion_desc
            if desire_summary:
                need_key = next((k for k in _NEED_DESC if k in desire_summary), "")
                if need_key:
                    desc += f"，{_NEED_DESC[need_key]}"

            template = _STYLE_FRAGMENTS.get(voice.style, _STYLE_FRAGMENTS[InnerVoiceStyle.PRESERVE])
            fragment = template.format(name=voice.name, desc=desc)
            fragment = fragment[:50]

            fragments.append((weight, fragment))

        if not fragments:
            return self._fallback_text

        fragments.sort(key=lambda x: -x[0])
        parts = [f for _, f in fragments[:3]]
        return "；".join(parts)

    def _apply_style(self, style: InnerVoiceStyle, intensity: float) -> float:
        match style:
            case InnerVoiceStyle.AMPLIFY:
                return min(100.0, intensity * 1.5)
            case InnerVoiceStyle.NEUTRALIZE:
                return intensity * 0.5
            case InnerVoiceStyle.PRESERVE:
                return intensity
            case InnerVoiceStyle.INVERT:
                return 100.0 - intensity
            case InnerVoiceStyle.CHAOTIC:
                return max(0.0, min(100.0, intensity + random.uniform(-30, 30)))
            case _:
                return intensity

    def _render_template(
        self,
        emotion_state: Optional[object],
        desire_summary: str,
        current_context: str,
    ) -> str:
        try:
            dominant = "平静"
            if emotion_state is not None:
                de = getattr(emotion_state, "dominant_emotion", "calm")
                from src.maisaka.agent.emotion import EMOTION_LABELS_ZH
                dominant = EMOTION_LABELS_ZH.get(de, de)

            result = self._template_text
            result = result.replace("{emotion}", dominant)
            result = result.replace("{need}", desire_summary or "无特别想法")
            result = result.replace("{situation}", current_context or "日常")
            return result
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, "内心声音模板渲染失败", exception=exc)
            logger.warning("内心声音模板渲染失败: %s", exc)
            return self._fallback_text
