from __future__ import annotations

from enum import Enum


class Valence(str, Enum):
    """情感极性"""

    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    POSITIVE = "positive"

    @property
    def value_int(self) -> int:
        match self:
            case Valence.NEGATIVE:
                return -1
            case Valence.NEUTRAL:
                return 0
            case Valence.POSITIVE:
                return 1


class VoiceStyle(str, Enum):
    """内心声音处理风格"""

    AMPLIFY = "amplify"
    NEUTRALIZE = "neutralize"
    PRESERVE = "preserve"
    INVERT = "invert"
    CHAOTIC = "chaotic"


class TimeOfDay(str, Enum):
    """时段"""

    DAWN = "dawn"
    MORNING = "morning"
    NOON = "noon"
    AFTERNOON = "afternoon"
    EVENING = "evening"
    NIGHT = "night"
    UNKNOWN = "unknown"


class CognitiveType(str, Enum):
    """认知层类型"""

    IMMUTABLE_FACT = "immutable_fact"
    STABLE_TRAIT = "stable_trait"
    CURRENT_STATE = "current_state"
    ACTIVE_HYPOTHESIS = "active_hypothesis"


class LifecycleStatus(str, Enum):
    """生命周期阶段"""

    ACTIVE = "active"
    COOLING = "cooling"
    FROZEN = "frozen"
    TOMBSTONE = "tombstone"


class EmotionalAxis(str, Enum):
    """情感主轴"""

    BOND = "bond"
    VIGILANCE = "vigilance"
    CONFIDENCE = "confidence"
    HUMILITY = "humility"
    WARMTH = "warmth"
    MELANCHOLY = "melancholy"
    GROUNDED = "grounded"
    NONE = "none"