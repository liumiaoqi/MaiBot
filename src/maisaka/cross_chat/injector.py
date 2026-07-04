"""跨聊上下文注入器。

将共享的上下文摘要注入到 Planner 提示词中。
摘要超过30分钟未更新时标记为待更新。
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from .sharing import ContextSharingManager
from .summarizer import ContextSummary

logger = logging.getLogger(__name__)


class CrossChatContextInjector:
    """跨聊上下文注入器。"""

    STALE_THRESHOLD_SECONDS = 1800

    def __init__(self, sharing_manager: ContextSharingManager) -> None:
        self._sharing_manager = sharing_manager

    def build_injection_text(
        self,
        target_session_id: str,
        target_agent_id: str,
        target_is_group: bool = True,
    ) -> str:
        """构建注入到 Planner 提示词的跨聊上下文文本。

        Args:
            target_session_id: 目标会话ID。
            target_agent_id: 目标智能体ID。
            target_is_group: 目标是否为群聊。

        Returns:
            注入文本。
        """
        summaries = self._sharing_manager.get_shared_summaries(
            target_session_id=target_session_id,
            target_agent_id=target_agent_id,
            target_is_group=target_is_group,
        )

        if not summaries:
            return ""

        now = time.time()
        parts: list[str] = []

        for summary in summaries:
            stale = (now - summary.updated_at) > self.STALE_THRESHOLD_SECONDS
            stale_marker = "（待更新）" if stale else ""

            display_name = summary.session_id
            text = summary.to_text()
            if text:
                parts.append(f"[{display_name}]{stale_marker} {text}")

        if not parts:
            return ""

        header = "其他聊天流上下文参考："
        return header + "\n" + "\n".join(parts)

    def get_stale_sessions(self) -> list[str]:
        """获取需要更新摘要的会话列表。"""
        now = time.time()
        stale: list[str] = []

        for session_id, summary in self._sharing_manager._summaries.items():
            if (now - summary.updated_at) > self.STALE_THRESHOLD_SECONDS:
                stale.append(session_id)

        return stale