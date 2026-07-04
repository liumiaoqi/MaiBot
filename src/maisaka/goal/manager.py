"""Goal 管理器。

管理 Goal 的生命周期：创建、追踪、超时、关闭。
约束：max_react=3、同一会话单 Goal、30分钟超时。
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from .judge import GoalJudge
from .verdict import GoalVerdict, GoalVerdictStatus

logger = logging.getLogger(__name__)


class GoalType(str, Enum):
    """Goal 类型。"""

    PROACTIVE_CHAT = "proactive_chat"
    EMOTION_COMFORT = "emotion_comfort"
    RELATIONSHIP_ADVANCE = "relationship_advance"
    TOPIC_GUIDE = "topic_guide"


class GoalStatus(str, Enum):
    """Goal 状态。"""

    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass
class Goal:
    """Goal 实例。"""

    goal_id: str
    goal_type: GoalType
    session_id: str
    agent_id: str
    description: str = ""
    status: GoalStatus = GoalStatus.PENDING
    react_count: int = 0
    max_react: int = 3
    created_at: float = field(default_factory=time.time)
    timeout_at: float = 0.0
    verdict: Optional[GoalVerdict] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.timeout_at == 0.0:
            self.timeout_at = self.created_at + 1800

    @property
    def is_expired(self) -> bool:
        return time.time() > self.timeout_at

    @property
    def can_react(self) -> bool:
        return self.status == GoalStatus.ACTIVE and self.react_count < self.max_react


class GoalManager:
    """Goal 管理器。

    约束：
      - max_react=3
      - 同一会话同时只有一个 Goal
      - 30分钟超时后自动关闭
    """

    DEFAULT_TIMEOUT_SECONDS = 1800
    DEFAULT_MAX_REACT = 3

    def __init__(self, judge: GoalJudge | None = None) -> None:
        self._judge = judge or GoalJudge()
        self._active_goals: dict[str, Goal] = {}

    def create_goal(
        self,
        session_id: str,
        agent_id: str,
        goal_type: GoalType,
        description: str = "",
        max_react: int = 3,
        timeout_seconds: int = 1800,
    ) -> Goal | None:
        """创建新 Goal。

        同一会话同时只有一个 Goal。

        Returns:
            Goal 或 None（已有活跃 Goal 时）。
        """
        existing = self._active_goals.get(session_id)
        if existing is not None:
            if existing.status == GoalStatus.ACTIVE and not existing.is_expired:
                logger.debug(
                    "会话已有活跃Goal: session=%s goal=%s",
                    session_id,
                    existing.goal_id,
                )
                return None
            else:
                self._close_goal(existing, GoalVerdictStatus.CANCELLED)

        goal_id = f"goal:{agent_id}:{uuid.uuid4().hex[:8]}"
        now = time.time()
        goal = Goal(
            goal_id=goal_id,
            goal_type=goal_type,
            session_id=session_id,
            agent_id=agent_id,
            description=description,
            max_react=max_react,
            created_at=now,
            timeout_at=now + timeout_seconds,
        )
        goal.status = GoalStatus.ACTIVE
        self._active_goals[session_id] = goal

        logger.info(
            "Goal创建: id=%s type=%s session=%s agent=%s",
            goal_id,
            goal_type.value,
            session_id,
            agent_id,
        )
        return goal

    def get_active_goal(self, session_id: str) -> Goal | None:
        """获取会话的活跃 Goal。"""
        goal = self._active_goals.get(session_id)
        if goal is None:
            return None

        if goal.is_expired and goal.status == GoalStatus.ACTIVE:
            self._close_goal(goal, GoalVerdictStatus.TIMEOUT)
            return None

        return goal if goal.status == GoalStatus.ACTIVE else None

    def record_reaction(self, session_id: str) -> Goal | None:
        """记录一次 Goal 反应。"""
        goal = self.get_active_goal(session_id)
        if goal is None:
            return None

        goal.react_count += 1

        if goal.react_count >= goal.max_react:
            verdict = self._judge.evaluate(
                goal_id=goal.goal_id,
                goal_type=goal.goal_type.value,
                react_count=goal.react_count,
                max_react=goal.max_react,
                interaction_happened=True,
            )
            self._close_goal(goal, verdict.status)
            return None

        return goal

    def check_timeouts(self) -> list[Goal]:
        """检查并关闭超时的 Goal。"""
        timed_out: list[Goal] = []
        for session_id, goal in list(self._active_goals.items()):
            if goal.status == GoalStatus.ACTIVE and goal.is_expired:
                self._close_goal(goal, GoalVerdictStatus.TIMEOUT)
                timed_out.append(goal)
        return timed_out

    def _close_goal(self, goal: Goal, status: GoalVerdictStatus) -> None:
        """关闭 Goal。"""
        goal.status = GoalStatus(status.value)
        goal.verdict = GoalVerdict(
            goal_id=goal.goal_id,
            status=status,
            react_count=goal.react_count,
        )

        self._active_goals.pop(goal.session_id, None)

        logger.info(
            "Goal关闭: id=%s status=%s reacts=%d",
            goal.goal_id,
            status.value,
            goal.react_count,
        )