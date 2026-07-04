"""Goal Judge 评估器。

使用独立模型（temperature=0）评估 Goal 执行结果。
"""

from __future__ import annotations

import logging
from typing import Any

from .verdict import GoalVerdict, GoalVerdictStatus

logger = logging.getLogger(__name__)


class GoalJudge:
    """Goal 评估器，评估 Goal 是否达成。

    使用规则评估（无需额外 LLM 调用），基于交互次数和反馈信号判断。
    """

    def evaluate(
        self,
        goal_id: str,
        goal_type: str,
        react_count: int,
        max_react: int = 3,
        interaction_happened: bool = False,
        positive_signals: int = 0,
        negative_signals: int = 0,
    ) -> GoalVerdict:
        """评估 Goal 执行结果。

        Args:
            goal_id: Goal ID。
            goal_type: Goal 类型。
            react_count: 已反应次数。
            max_react: 最大反应次数。
            interaction_happened: 是否发生了有效互动。
            positive_signals: 正面信号数。
            negative_signals: 负面信号数。

        Returns:
            GoalVerdict: 判决结果。
        """
        if react_count >= max_react:
            if interaction_happened and positive_signals > negative_signals:
                return GoalVerdict(
                    goal_id=goal_id,
                    status=GoalVerdictStatus.ACHIEVED,
                    confidence=min(0.5 + positive_signals * 0.15, 1.0),
                    evidence=f"达到最大反应次数{max_react}，正面信号{positive_signals}个",
                    react_count=react_count,
                )
            elif interaction_happened:
                return GoalVerdict(
                    goal_id=goal_id,
                    status=GoalVerdictStatus.PARTIAL,
                    confidence=0.4,
                    evidence=f"达到最大反应次数{max_react}，有互动但信号不足",
                    react_count=react_count,
                )
            else:
                return GoalVerdict(
                    goal_id=goal_id,
                    status=GoalVerdictStatus.FAILED,
                    confidence=0.2,
                    evidence=f"达到最大反应次数{max_react}，无有效互动",
                    react_count=react_count,
                )

        if positive_signals >= 2:
            return GoalVerdict(
                goal_id=goal_id,
                status=GoalVerdictStatus.ACHIEVED,
                confidence=min(0.6 + positive_signals * 0.1, 1.0),
                evidence=f"正面信号{positive_signals}个，Goal已达成",
                react_count=react_count,
            )

        if negative_signals >= 2:
            return GoalVerdict(
                goal_id=goal_id,
                status=GoalVerdictStatus.FAILED,
                confidence=0.7,
                evidence=f"负面信号{negative_signals}个，Goal已失败",
                react_count=react_count,
            )

        return GoalVerdict(
            goal_id=goal_id,
            status=GoalVerdictStatus.PARTIAL,
            confidence=0.3,
            evidence="评估中，信号不足",
            react_count=react_count,
        )