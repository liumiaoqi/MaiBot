"""共享范围管理。

管理共享范围。私聊摘要标记为 is_private=True，不共享到任何群聊。
禁止跨智能体共享上下文摘要。
"""

from __future__ import annotations

import logging
from typing import Optional

from .summarizer import ContextSummary

logger = logging.getLogger(__name__)


class ContextSharingManager:
    """上下文共享范围管理器。"""

    def __init__(self) -> None:
        self._summaries: dict[str, ContextSummary] = {}

    def store_summary(self, summary: ContextSummary) -> None:
        """存储上下文摘要。"""
        self._summaries[summary.session_id] = summary

    def get_shared_summaries(
        self,
        target_session_id: str,
        target_agent_id: str,
        target_is_group: bool = True,
    ) -> list[ContextSummary]:
        """获取可共享到目标会话的摘要列表。

        规则：
          1. 私聊摘要不共享到任何群聊
          2. 禁止跨智能体共享
          3. 不包含目标会话自身的摘要

        Args:
            target_session_id: 目标会话ID。
            target_agent_id: 目标智能体ID。
            target_is_group: 目标是否为群聊。

        Returns:
            可共享的摘要列表。
        """
        results: list[ContextSummary] = []

        for session_id, summary in self._summaries.items():
            if session_id == target_session_id:
                continue

            if summary.is_private and target_is_group:
                continue

            if summary.agent_id != target_agent_id:
                continue

            results.append(summary)

        return results

    def remove_summary(self, session_id: str) -> None:
        """移除摘要。"""
        self._summaries.pop(session_id, None)

    def get_summary(self, session_id: str) -> ContextSummary | None:
        """获取指定会话的摘要。"""
        return self._summaries.get(session_id)