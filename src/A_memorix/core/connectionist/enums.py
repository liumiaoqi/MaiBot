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