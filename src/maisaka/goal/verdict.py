"""Goal 判决结果。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class GoalVerdictStatus(str, Enum):
    """Goal 判决状态。"""

    ACHIEVED = "achieved"
    PARTIAL = "partial"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass
class GoalVerdict:
    """Goal 判决结果。"""

    goal_id: str
    status: GoalVerdictStatus = GoalVerdictStatus.FAILED
    confidence: float = 0.0
    evidence: str = ""
    react_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_terminal(self) -> bool:
        """是否为终态。"""
        return self.status in (
            GoalVerdictStatus.ACHIEVED,
            GoalVerdictStatus.FAILED,
            GoalVerdictStatus.TIMEOUT,
            GoalVerdictStatus.CANCELLED,
        )