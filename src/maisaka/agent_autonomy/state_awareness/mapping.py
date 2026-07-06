"""数值→自然语言映射——生命力等级与情绪倾向。"""

from __future__ import annotations

from enum import Enum


class VitalityLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


_VITALITY_HIGH_THRESHOLD = 60.0
_VITALITY_LOW_THRESHOLD = 30.0
_EMOTION_TENDENCY_THRESHOLD = 50.0


class VitalityLevelMapping:
    """生命力值→等级→自然语言描述。"""

    def map_to_level(self, vitality: float) -> VitalityLevel:
        if vitality >= _VITALITY_HIGH_THRESHOLD:
            return VitalityLevel.HIGH
        if vitality < _VITALITY_LOW_THRESHOLD:
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

    def map_to_tendency(self, emotion_type: str, intensity: float) -> str:
        if intensity < _EMOTION_TENDENCY_THRESHOLD:
            return ""

        if emotion_type in ("happy", "excited"):
            if emotion_type == "excited" and intensity >= _EMOTION_TENDENCY_THRESHOLD + 20:
                return "很兴奋"
            return "心情不错"
        if emotion_type in ("sad", "lonely"):
            if emotion_type == "lonely" and intensity >= _EMOTION_TENDENCY_THRESHOLD + 20:
                return "似乎有点孤单"
            return "有些低落"
        if emotion_type in ("angry", "anxious"):
            if emotion_type == "anxious" and intensity >= _EMOTION_TENDENCY_THRESHOLD + 20:
                return "看起来有些不安"
            return "似乎有些烦躁"
        return ""
