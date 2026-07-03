"""关系管理器，管理智能体与用户的关系进展。"""

from __future__ import annotations

import time
from typing import Optional

from src.common.logger import get_logger

from .level import LEVEL_THRESHOLDS, RelationshipLevel, RelationshipSnapshot

logger = get_logger("maisaka_relationship")

_RELATIONSHIP_STORE: dict[str, RelationshipSnapshot] = {}

_DECAY_7D = 10.0
_DECAY_30D = 30.0
_DECAY_90D = 50.0


def _store_key(agent_id: str, user_id: str) -> str:
    return f"{agent_id}:{user_id}"


class RelationshipManager:
    """管理智能体与用户的关系进展。"""

    def __init__(self) -> None:
        self._emotion_trigger_callback: Optional[object] = None

    def set_emotion_trigger_callback(self, callback: object) -> None:
        """设置情绪触发回调，用于关系-情绪联动。"""
        self._emotion_trigger_callback = callback

    def get_relationship(self, agent_id: str, user_id: str) -> RelationshipSnapshot:
        """获取智能体与用户的关系快照。"""
        key = _store_key(agent_id, user_id)
        snapshot = _RELATIONSHIP_STORE.get(key)
        if snapshot is not None:
            self._apply_time_decay(snapshot)
            return snapshot.model_copy()

        return RelationshipSnapshot(
            agent_id=agent_id,
            user_id=user_id,
            created_at=time.time(),
        )

    def update_interaction(
        self,
        agent_id: str,
        user_id: str,
        *,
        frequency_weight: float = 0.3,
        depth_weight: float = 0.3,
        emotion_weight: float = 0.2,
        time_weight: float = 0.2,
        is_positive_emotion: bool = True,
        message_length: int = 0,
    ) -> RelationshipSnapshot:
        """更新互动记录并计算关系进展。"""
        key = _store_key(agent_id, user_id)
        snapshot = _RELATIONSHIP_STORE.get(key)
        if snapshot is None:
            snapshot = RelationshipSnapshot(
                agent_id=agent_id,
                user_id=user_id,
                created_at=time.time(),
            )

        self._apply_time_decay(snapshot)

        frequency_delta = frequency_weight * 5.0
        depth_delta = depth_weight * min(10.0, message_length / 20.0)
        emotion_delta = emotion_weight * (8.0 if is_positive_emotion else -3.0)
        time_delta = time_weight * 3.0

        growth_rate = self._get_growth_rate(agent_id)
        total_delta = (frequency_delta + depth_delta + emotion_delta + time_delta) * growth_rate

        old_level = snapshot.level
        snapshot.update_score(total_delta)
        snapshot.interaction_count += 1
        snapshot.last_interaction_at = time.time()

        _RELATIONSHIP_STORE[key] = snapshot

        if snapshot.level != old_level and snapshot.level > old_level:
            self._on_relationship_upgrade(snapshot, old_level)

        return snapshot.model_copy()

    def _apply_time_decay(self, snapshot: RelationshipSnapshot) -> None:
        """按时间衰减关系分数。"""
        if snapshot.last_interaction_at <= 0:
            return

        now = time.time()
        elapsed_days = (now - snapshot.last_interaction_at) / 86400.0

        if elapsed_days < 7:
            return

        decay = 0.0
        if elapsed_days >= 90:
            decay = _DECAY_90D
        elif elapsed_days >= 30:
            decay = _DECAY_30D
        elif elapsed_days >= 7:
            decay = _DECAY_7D

        if decay > 0:
            snapshot.update_score(-decay)
            if snapshot.score <= LEVEL_THRESHOLDS.get(RelationshipLevel.ACQUAINTANCE, 350):
                snapshot.score = max(0.0, snapshot.score)

    def _on_relationship_upgrade(self, snapshot: RelationshipSnapshot, old_level: RelationshipLevel) -> None:
        """关系升级时的联动处理。"""
        logger.info(
            f"关系升级: {snapshot.agent_id} <-> {snapshot.user_id} "
            f"{old_level.label_zh()} -> {snapshot.level.label_zh()}"
        )

        if self._emotion_trigger_callback and callable(self._emotion_trigger_callback):
            try:
                self._emotion_trigger_callback("happy", 10.0)
            except Exception:
                pass

    @staticmethod
    def _get_growth_rate(agent_id: str) -> float:
        """获取智能体的关系进展速率。"""
        try:
            from src.maisaka.agent.registry import AgentConfigRegistry

            registry = AgentConfigRegistry()
            if registry.has_agent(agent_id):
                return registry.get_agent(agent_id).relationship_growth_rate
        except Exception:
            pass
        return 1.0
