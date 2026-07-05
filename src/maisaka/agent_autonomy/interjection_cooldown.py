"""插话冷却管理器——按智能体+会话管理插话冷却时间和频率限制。"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from src.common.logger import get_logger
from src.config.config import global_config

logger = get_logger("agent_autonomy.interjection_cooldown")


class InterjectionCooldownManager:
    """插话冷却管理器。"""

    def __init__(self) -> None:
        # (session_id, agent_id) -> last_interjection_at
        self._last_interjection: dict[tuple[str, str], datetime] = {}
        # (session_id, agent_id) -> [interjection_times]
        self._interjection_history: dict[tuple[str, str], list[datetime]] = {}
        # session_id -> [interjection_times]
        self._session_history: dict[str, list[datetime]] = {}

    def can_interject(self, session_id: str, agent_id: str) -> bool:
        """检查智能体是否可以插话。"""
        config = global_config.agent_autonomy

        # 检查冷却时间
        key = (session_id, agent_id)
        last_time = self._last_interjection.get(key)
        if last_time is not None:
            cooldown = timedelta(minutes=config.interjection_cooldown_minutes)
            if datetime.now() - last_time < cooldown:
                return False

        # 检查智能体频率限制
        history = self._interjection_history.get(key, [])
        cutoff = datetime.now() - timedelta(hours=1)
        recent_count = sum(1 for t in history if t >= cutoff)
        if recent_count >= config.max_interjections_per_hour:
            return False

        # 检查会话频率限制
        session_history = self._session_history.get(session_id, [])
        session_recent = sum(1 for t in session_history if t >= cutoff)
        if session_recent >= config.max_interjections_per_session_per_hour:
            return False

        return True

    def record_interjection(self, session_id: str, agent_id: str) -> None:
        """记录一次插话。"""
        now = datetime.now()
        key = (session_id, agent_id)

        self._last_interjection[key] = now

        if key not in self._interjection_history:
            self._interjection_history[key] = []
        self._interjection_history[key].append(now)

        if session_id not in self._session_history:
            self._session_history[session_id] = []
        self._session_history[session_id].append(now)

    def get_cooldown_remaining(self, session_id: str, agent_id: str) -> float:
        """获取剩余冷却时间（秒）。"""
        config = global_config.agent_autonomy
        key = (session_id, agent_id)
        last_time = self._last_interjection.get(key)
        if last_time is None:
            return 0.0

        cooldown = timedelta(minutes=config.interjection_cooldown_minutes)
        elapsed = datetime.now() - last_time
        remaining = (cooldown - elapsed).total_seconds()
        return max(0.0, remaining)

    def get_session_interjection_count(self, session_id: str, hours: float = 1.0) -> int:
        """获取会话在指定时间窗口内的插话总次数。"""
        history = self._session_history.get(session_id, [])
        cutoff = datetime.now() - timedelta(hours=hours)
        return sum(1 for t in history if t >= cutoff)