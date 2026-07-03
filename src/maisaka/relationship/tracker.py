"""关系轨迹追踪，记录关系变化的历史事件。"""

from __future__ import annotations

import time

from pydantic import BaseModel, Field

from src.common.logger import get_logger

from .level import RelationshipLevel

logger = get_logger("maisaka_relationship_tracker")


class RelationshipEvent(BaseModel):
    """关系变化事件。"""

    agent_id: str = Field(default="", description="智能体ID")
    user_id: str = Field(default="", description="用户ID")
    event_type: str = Field(default="", description="事件类型: upgrade/downgrade/decay/interaction_milestone")
    old_level: RelationshipLevel = Field(default=RelationshipLevel.STRANGER, description="变化前等级")
    new_level: RelationshipLevel = Field(default=RelationshipLevel.STRANGER, description="变化后等级")
    old_score: float = Field(default=0.0, description="变化前分数")
    new_score: float = Field(default=0.0, description="变化后分数")
    timestamp: float = Field(default=0.0, description="事件时间戳")

    def to_text(self) -> str:
        """生成事件描述文本。"""
        ts_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(self.timestamp)) if self.timestamp > 0 else "未知时间"
        if self.event_type == "upgrade":
            return f"[{ts_str}] 关系升级: {self.old_level.label_zh()} -> {self.new_level.label_zh()}"
        if self.event_type == "downgrade":
            return f"[{ts_str}] 关系降级: {self.old_level.label_zh()} -> {self.new_level.label_zh()}"
        if self.event_type == "decay":
            return f"[{ts_str}] 关系自然衰减: {self.old_score:.0f} -> {self.new_score:.0f}"
        if self.event_type == "interaction_milestone":
            return f"[{ts_str}] 互动里程碑: 累计互动{int(self.new_score)}次"
        return f"[{ts_str}] {self.event_type}"


class RelationshipTracker:
    """关系轨迹追踪器，记录关系变化历史。"""

    _MAX_IN_MEMORY = 50

    def __init__(self) -> None:
        self._events: list[RelationshipEvent] = []

    def record_level_change(
        self,
        agent_id: str,
        user_id: str,
        old_level: RelationshipLevel,
        new_level: RelationshipLevel,
        old_score: float,
        new_score: float,
    ) -> None:
        """记录等级变化事件。"""
        event_type = "upgrade" if new_level > old_level else "downgrade"
        event = RelationshipEvent(
            agent_id=agent_id,
            user_id=user_id,
            event_type=event_type,
            old_level=old_level,
            new_level=new_level,
            old_score=old_score,
            new_score=new_score,
            timestamp=time.time(),
        )
        self._append(event)
        logger.info(f"关系轨迹: {agent_id} <-> {user_id} {event.to_text()}")

    def record_decay(
        self,
        agent_id: str,
        user_id: str,
        old_score: float,
        new_score: float,
    ) -> None:
        """记录自然衰减事件。"""
        event = RelationshipEvent(
            agent_id=agent_id,
            user_id=user_id,
            event_type="decay",
            old_score=old_score,
            new_score=new_score,
            timestamp=time.time(),
        )
        self._append(event)

    def record_milestone(
        self,
        agent_id: str,
        user_id: str,
        interaction_count: int,
    ) -> None:
        """记录互动里程碑（每100次）。"""
        if interaction_count % 100 != 0 or interaction_count == 0:
            return
        event = RelationshipEvent(
            agent_id=agent_id,
            user_id=user_id,
            event_type="interaction_milestone",
            new_score=float(interaction_count),
            timestamp=time.time(),
        )
        self._append(event)

    def get_recent_events(self, agent_id: str, user_id: str, limit: int = 10) -> list[RelationshipEvent]:
        """获取最近的关系变化事件。"""
        filtered = [e for e in self._events if e.agent_id == agent_id and e.user_id == user_id]
        return filtered[-limit:]

    def get_trajectory_text(self, agent_id: str, user_id: str, limit: int = 5) -> str:
        """生成关系轨迹描述文本，用于提示词注入。"""
        events = self.get_recent_events(agent_id, user_id, limit)
        if not events:
            return ""
        lines = [e.to_text() for e in events]
        return "关系变化轨迹:\n" + "\n".join(lines)

    def _append(self, event: RelationshipEvent) -> None:
        """添加事件并维护内存上限。"""
        self._events.append(event)
        if len(self._events) > self._MAX_IN_MEMORY:
            self._events = self._events[-self._MAX_IN_MEMORY:]