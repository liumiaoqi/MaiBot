"""关系管理器，管理智能体与用户的关系进展。"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Optional

from src.common.database.database import get_db_session
from src.common.database.database_model import AgentRelationship
from src.common.logger import get_logger

from .level import LEVEL_THRESHOLDS, RelationshipLevel, RelationshipSnapshot
from .tracker import RelationshipTracker

logger = get_logger("maisaka_relationship")

_DECAY_7D = 10.0
_DECAY_30D = 30.0
_DECAY_90D = 50.0


class RelationshipManager:
    """管理智能体与用户的关系进展，数据持久化到数据库。"""

    def __init__(self) -> None:
        self._emotion_trigger_callback: Optional[object] = None
        self._tracker = RelationshipTracker()

    def set_emotion_trigger_callback(self, callback: object) -> None:
        """设置情绪触发回调，用于关系-情绪联动。"""
        self._emotion_trigger_callback = callback

    def get_trajectory_text(self, agent_id: str, user_id: str, limit: int = 5) -> str:
        """获取关系轨迹描述文本。"""
        return self._tracker.get_trajectory_text(agent_id, user_id, limit)

    def get_relationship(self, agent_id: str, user_id: str) -> RelationshipSnapshot:
        """获取智能体与用户的关系快照。"""
        row = self._load_row(agent_id, user_id)
        if row is not None:
            snapshot = self._row_to_snapshot(row)
            self._apply_time_decay(snapshot, agent_id, user_id)
            return snapshot

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
        row = self._load_row(agent_id, user_id)
        if row is not None:
            snapshot = self._row_to_snapshot(row)
        else:
            snapshot = RelationshipSnapshot(
                agent_id=agent_id,
                user_id=user_id,
                created_at=time.time(),
            )

        self._apply_time_decay(snapshot, agent_id, user_id)

        frequency_delta = frequency_weight * 5.0
        depth_delta = depth_weight * min(10.0, message_length / 20.0)
        emotion_delta = emotion_weight * (8.0 if is_positive_emotion else -3.0)
        time_delta = time_weight * 3.0

        growth_rate = self._get_growth_rate(agent_id)
        total_delta = (frequency_delta + depth_delta + emotion_delta + time_delta) * growth_rate

        old_level = snapshot.level
        old_score = snapshot.score
        snapshot.update_score(total_delta)
        snapshot.interaction_count += 1
        snapshot.last_interaction_at = time.time()

        self._save_snapshot(agent_id, user_id, snapshot)

        if snapshot.level != old_level:
            self._tracker.record_level_change(
                agent_id, user_id, old_level, snapshot.level, old_score, snapshot.score,
            )
            if snapshot.level > old_level:
                self._on_relationship_upgrade(snapshot, old_level)

        self._tracker.record_milestone(agent_id, user_id, snapshot.interaction_count)

        return snapshot.model_copy()

    @staticmethod
    def _load_row(agent_id: str, user_id: str) -> Optional[AgentRelationship]:
        """从数据库加载关系记录。"""
        try:
            with get_db_session() as session:
                return (
                    session.query(AgentRelationship)
                    .filter(
                        AgentRelationship.agent_id == agent_id,
                        AgentRelationship.user_id == user_id,
                    )
                    .first()
                )
        except Exception:
            logger.warning(f"加载关系记录失败: {agent_id} <-> {user_id}")
            return None

    @staticmethod
    def _save_snapshot(agent_id: str, user_id: str, snapshot: RelationshipSnapshot) -> None:
        """将关系快照持久化到数据库。"""
        try:
            with get_db_session() as session:
                row = (
                    session.query(AgentRelationship)
                    .filter(
                        AgentRelationship.agent_id == agent_id,
                        AgentRelationship.user_id == user_id,
                    )
                    .first()
                )
                now = datetime.now()
                if row is None:
                    row = AgentRelationship(
                        agent_id=agent_id,
                        user_id=user_id,
                        score=snapshot.score,
                        level=snapshot.level,
                        interaction_count=snapshot.interaction_count,
                        last_interaction_at=now,
                        created_at=now,
                    )
                    session.add(row)
                else:
                    row.score = snapshot.score
                    row.level = snapshot.level
                    row.interaction_count = snapshot.interaction_count
                    row.last_interaction_at = now
        except Exception:
            logger.warning(f"保存关系记录失败: {agent_id} <-> {user_id}")

    @staticmethod
    def _row_to_snapshot(row: AgentRelationship) -> RelationshipSnapshot:
        """将数据库行转换为关系快照。"""
        return RelationshipSnapshot(
            agent_id=row.agent_id,
            user_id=row.user_id,
            score=row.score,
            level=RelationshipLevel(row.level),
            interaction_count=row.interaction_count,
            last_interaction_at=row.last_interaction_at.timestamp() if row.last_interaction_at else 0.0,
            created_at=row.created_at.timestamp() if row.created_at else 0.0,
        )

    def _apply_time_decay(self, snapshot: RelationshipSnapshot, agent_id: str = "", user_id: str = "") -> None:
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
            old_score = snapshot.score
            snapshot.update_score(-decay)
            if snapshot.score <= LEVEL_THRESHOLDS.get(RelationshipLevel.ACQUAINTANCE, 350):
                snapshot.score = max(0.0, snapshot.score)
            self._tracker.record_decay(agent_id, user_id, old_score, snapshot.score)

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

            registry = AgentConfigRegistry.get_instance()
            if registry.has_agent(agent_id):
                return registry.get_agent(agent_id).relationship_growth_rate
        except Exception:
            pass
        return 1.0
