from __future__ import annotations

from src.common.logger import get_logger

from ..connectionist.enums import VoiceStyle
from ..connectionist.models import InnerVoice, MemoryPersonalityV2

logger = get_logger("PersonalityRegistry")

_DEFAULT_PERSONALITY = MemoryPersonalityV2()
_DEFAULT_VOICE = InnerVoice(name="default", style=VoiceStyle.PRESERVE)


class PersonalityRegistry:
    """智能体记忆性格注册表"""

    def __init__(self) -> None:
        self._personalities: dict[str, MemoryPersonalityV2] = {}
        self._voices: dict[str, list[InnerVoice]] = {}

    def register_agent(self, agent_id: str, personality: MemoryPersonalityV2, voices: list[InnerVoice]) -> None:
        self._personalities[agent_id] = personality
        self._voices[agent_id] = voices
        logger.info(f"注册智能体记忆性格: {agent_id}, 衰减率={personality.decay_rate}, 情感敏感度={personality.emotional_sensitivity}, 声音数={len(voices)}")

    def get_personality(self, agent_id: str) -> MemoryPersonalityV2:
        if agent_id in self._personalities:
            return self._personalities[agent_id]
        logger.warning(f"智能体 {agent_id} 未注册记忆性格，使用默认值")
        return _DEFAULT_PERSONALITY

    def get_voices(self, agent_id: str) -> list[InnerVoice]:
        if agent_id in self._voices:
            return self._voices[agent_id]
        return [_DEFAULT_VOICE]

    def registered_agents(self) -> list[str]:
        return list(self._personalities.keys())