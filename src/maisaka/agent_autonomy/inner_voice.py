from __future__ import annotations

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
    ) -> str:
        if self._inner_voices:
            return self._generate_multi_voice(emotion_state, desire_summary, memory_personality)
        if self._template_text:
            return self._render_template(emotion_state, desire_summary, current_context)
        return self._fallback_text

    def _generate_multi_voice(
        self,
        emotion_state: Optional[object],
        desire_summary: str,
        memory_personality: Optional[MemoryPersonalityV2],
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

            processed_emotion = self._apply_style(voice.style, dominant_intensity)
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
        if style == InnerVoiceStyle.AMPLIFY:
            return min(100.0, intensity * 1.5)
        if style == InnerVoiceStyle.NEUTRALIZE:
            return intensity * 0.5
        if style == InnerVoiceStyle.PRESERVE:
            return intensity
        if style == InnerVoiceStyle.INVERT:
            return 100.0 - intensity
        if style == InnerVoiceStyle.CHAOTIC:
            return max(0.0, min(100.0, intensity + random.uniform(-30, 30)))
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
            logger.warning("内心声音模板渲染失败: %s", exc)
            return self._fallback_text