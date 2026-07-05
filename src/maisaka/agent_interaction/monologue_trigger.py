"""内心独白触发器。

当智能体空闲超过阈值且主导情绪强度超过阈值时，
触发内心独白。同一智能体的内心独白有冷却期。
"""

from __future__ import annotations

import time

from src.maisaka.agent.emotion import EmotionState

# 默认阈值
_DEFAULT_IDLE_THRESHOLD_MINUTES = 30
_DEFAULT_EMOTION_INTENSITY_THRESHOLD = 40
_DEFAULT_MIN_INTERVAL_MINUTES = 15


class MonologueTrigger:
    """内心独白触发器。

    触发条件：
    1. 空闲时间 ≥ idle_threshold_minutes（默认30分钟）
    2. 主导情绪强度 > emotion_intensity_threshold（默认40）
    3. 距上次内心独白 ≥ min_interval_minutes（默认15分钟）
    """

    def __init__(
        self,
        idle_threshold_minutes: float = _DEFAULT_IDLE_THRESHOLD_MINUTES,
        emotion_intensity_threshold: int = _DEFAULT_EMOTION_INTENSITY_THRESHOLD,
        min_interval_minutes: float = _DEFAULT_MIN_INTERVAL_MINUTES,
    ) -> None:
        self._idle_threshold = idle_threshold_minutes
        self._emotion_threshold = emotion_intensity_threshold
        self._min_interval = min_interval_minutes
        # 每个智能体最后活跃时间
        self._last_active_at: dict[str, float] = {}
        # 每个智能体最后内心独白时间
        self._last_monologue_at: dict[str, float] = {}

    def should_trigger(
        self, agent_id: str, idle_minutes: float, emotion_state: EmotionState
    ) -> bool:
        """判断是否应触发内心独白。"""
        # 情绪强度检查
        intensity = emotion_state.get_dominant_intensity()
        if intensity <= self._emotion_threshold:
            return False

        # 空闲时间检查
        if idle_minutes < self._idle_threshold:
            return False

        # 冷却期检查
        now = time.time()
        last = self._last_monologue_at.get(agent_id, 0.0)
        if (now - last) < self._min_interval * 60:
            return False

        return True

    def record_activity(self, agent_id: str) -> None:
        """记录智能体活跃（对话或交互），重置空闲计时。"""
        self._last_active_at[agent_id] = time.time()

    def record_monologue(self, agent_id: str) -> None:
        """记录内心独白触发，更新冷却计时。"""
        self._last_monologue_at[agent_id] = time.time()

    def get_idle_minutes(self, agent_id: str) -> float:
        """获取智能体空闲分钟数。"""
        last = self._last_active_at.get(agent_id, 0.0)
        if last == 0.0:
            return 0.0
        return (time.time() - last) / 60.0