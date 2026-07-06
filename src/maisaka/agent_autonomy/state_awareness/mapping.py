"""数值→自然语言映射——生命力等级与情绪倾向。"""

from __future__ import annotations

from enum import Enum

from src.config.config import global_config


class VitalityLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class VitalityLevelMapping:
    """生命力值→等级→自然语言描述。"""

    def __init__(self) -> None:
        self._config = global_config.agent_autonomy

    def map_to_level(self, vitality: float) -> VitalityLevel:
        if vitality >= self._config.vitality_level_high_threshold:
            return VitalityLevel.HIGH
        if vitality < self._config.vitality_level_low_threshold:
            return VitalityLevel.LOW
        return VitalityLevel.MEDIUM

    def map_to_description(self, level: VitalityLevel, state: str) -> str:
        """等级+状态映射为自然语言描述。"""
        if state == "active":
            if level == VitalityLevel.HIGH:
                return "也在场，精神饱满"
            if level == VitalityLevel.MEDIUM:
                return "也在场"
            return "也在场，似乎有些疲倦"
        if state == "standby":
            if level == VitalityLevel.HIGH:
                return "在旁边听着，跃跃欲试"
            if level == VitalityLevel.MEDIUM:
                return "在旁边安静地听着"
            return "在旁边待着，有些困倦"
        return ""


class EmotionTendencyMapping:
    """情绪类型+强度→自然语言倾向描述。"""

    def __init__(self) -> None:
        self._config = global_config.agent_autonomy
        self._threshold = self._config.emotion_tendency_threshold

    def map_to_tendency(self, emotion_type: str, intensity: float) -> str:
        if intensity < self._threshold:
            return ""

        if emotion_type in ("happy", "excited"):
            if emotion_type == "excited" and intensity >= self._threshold + 20:
                return "很兴奋"
            return "心情不错"
        if emotion_type in ("sad", "lonely"):
            if emotion_type == "lonely" and intensity >= self._threshold + 20:
                return "似乎有点孤单"
            return "有些低落"
        if emotion_type in ("angry", "anxious"):
            if emotion_type == "anxious" and intensity >= self._threshold + 20:
                return "看起来有些不安"
            return "似乎有些烦躁"
        return ""