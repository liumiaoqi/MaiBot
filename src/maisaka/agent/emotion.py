"""智能体情绪状态管理。"""

from __future__ import annotations

import math
import time
from typing import Optional

from pydantic import BaseModel, Field

from .config import AgentConfig, EmotionBehaviorRule

EMOTION_TYPES = ("happy", "sad", "anxious", "angry", "calm", "excited", "lonely")

EMOTION_LABELS_ZH = {
    "happy": "开心",
    "sad": "难过",
    "anxious": "焦虑",
    "angry": "生气",
    "calm": "平静",
    "excited": "兴奋",
    "lonely": "孤独",
}


class EmotionState(BaseModel):
    """智能体当前情绪状态快照。"""

    emotions: dict[str, float] = Field(
        default_factory=lambda: {e: 0.0 for e in EMOTION_TYPES},
        description="各情绪维度的当前强度 (0-100)",
    )
    dominant_emotion: str = Field(default="calm", description="主导情绪类型")
    updated_at: float = Field(default_factory=time.time, description="最后更新时间戳")

    def get_dominant(self) -> str:
        """返回强度最高的情绪类型。"""
        if not self.emotions:
            return "calm"
        return max(self.emotions, key=self.emotions.get)

    def get_intensity(self, emotion_type: str) -> float:
        """返回指定情绪的当前强度。"""
        return self.emotions.get(emotion_type, 0.0)

    def get_dominant_intensity(self) -> float:
        """返回主导情绪的强度。"""
        return self.emotions.get(self.dominant_emotion, 0.0)

    def to_prompt_text(self) -> str:
        """生成用于提示词注入的情绪状态描述。"""
        dominant_label = EMOTION_LABELS_ZH.get(self.dominant_emotion, self.dominant_emotion)
        intensity = self.get_dominant_intensity()

        if intensity < 10:
            return "当前心情：平静"

        parts = [f"当前心情：{dominant_label}（强度{intensity:.0f}/100）"]

        secondary = []
        for etype, val in sorted(self.emotions.items(), key=lambda x: -x[1]):
            if etype != self.dominant_emotion and val >= 15:
                secondary.append(f"{EMOTION_LABELS_ZH.get(etype, etype)}({val:.0f})")
        if secondary:
            parts.append(f"同时感受到：{'、'.join(secondary)}")

        return "。".join(parts)


class EmotionManager:
    """管理单个会话中智能体的情绪状态。"""

    def __init__(self, agent_config: AgentConfig) -> None:
        self._config = agent_config
        baseline = agent_config.emotion_baseline
        self._state = EmotionState(
            emotions={e: float(baseline.get(e, 0)) for e in EMOTION_TYPES},
        )
        self._state.dominant_emotion = self._state.get_dominant()
        self._last_decay_time = time.time()

    @property
    def state(self) -> EmotionState:
        """返回当前情绪状态（自动衰减后）。"""
        self._apply_decay()
        return self._state

    def apply_trigger(self, emotion_type: str, delta: float) -> None:
        """触发情绪变化。

        Args:
            emotion_type: 情绪类型
            delta: 变化量，正数增强，负数减弱
        """
        if emotion_type not in EMOTION_TYPES:
            return

        self._apply_decay()
        current = self._state.emotions.get(emotion_type, 0.0)
        new_val = max(0.0, min(100.0, current + delta))
        self._state.emotions[emotion_type] = new_val
        self._state.dominant_emotion = self._state.get_dominant()
        self._state.updated_at = time.time()

    def apply_event_trigger(self, event_type: str) -> None:
        """根据群事件类型触发情绪变化。"""
        for rule in self._config.event_reaction_rules:
            if rule.event_type == event_type:
                for emotion, intensity in rule.emotion_trigger.items():
                    self.apply_trigger(emotion, float(intensity))

    def get_behavior_tendency(self) -> Optional[EmotionBehaviorRule]:
        """根据当前主导情绪获取行为倾向。"""
        self._apply_decay()
        dominant = self._state.dominant_emotion
        intensity = self._state.get_dominant_intensity()

        for rule in self._config.emotion_behavior_map:
            if rule.emotion_type == dominant and intensity >= rule.intensity_threshold:
                return rule
        return None

    def reset_to_baseline(self) -> None:
        """重置到基线情绪状态。"""
        baseline = self._config.emotion_baseline
        self._state = EmotionState(
            emotions={e: float(baseline.get(e, 0)) for e in EMOTION_TYPES},
        )
        self._state.dominant_emotion = self._state.get_dominant()
        self._last_decay_time = time.time()

    def _apply_decay(self) -> None:
        """按时间衰减情绪强度，趋向基线。"""
        now = time.time()
        elapsed_hours = (now - self._last_decay_time) / 3600.0
        if elapsed_hours < 0.01:
            return

        self._last_decay_time = now
        decay_rate = self._config.emotion_decay_rate
        baseline = self._config.emotion_baseline

        decay_factor = math.exp(-decay_rate * elapsed_hours)

        for etype in EMOTION_TYPES:
            current = self._state.emotions.get(etype, 0.0)
            base = float(baseline.get(etype, 0))
            decayed = base + (current - base) * decay_factor
            self._state.emotions[etype] = max(0.0, min(100.0, decayed))

        self._state.dominant_emotion = self._state.get_dominant()