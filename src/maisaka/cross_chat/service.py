"""跨聊上下文服务。

整合摘要生成+共享管理+注入。
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .injector import CrossChatContextInjector
from .sharing import ContextSharingManager
from .summarizer import ContextSummarizer, ContextSummary

logger = logging.getLogger(__name__)


class CrossChatContextService:
    """跨聊上下文服务。"""

    def __init__(self) -> None:
        self._summarizer = ContextSummarizer()
        self._sharing_manager = ContextSharingManager()
        self._injector = CrossChatContextInjector(self._sharing_manager)

    def update_summary(
        self,
        session_id: str,
        agent_id: str,
        messages: list[dict[str, Any]],
        is_private: bool = False,
    ) -> ContextSummary | None:
        """更新会话的上下文摘要。"""
        summary = self._summarizer.generate_summary(
            session_id=session_id,
            agent_id=agent_id,
            messages=messages,
            is_private=is_private,
        )

        if summary is not None:
            self._sharing_manager.store_summary(summary)

        return summary

    def get_cross_chat_context(
        self,
        target_session_id: str,
        target_agent_id: str,
        target_is_group: bool = True,
    ) -> str:
        """获取注入到目标会话的跨聊上下文文本。"""
        return self._injector.build_injection_text(
            target_session_id=target_session_id,
            target_agent_id=target_agent_id,
            target_is_group=target_is_group,
        )

    def get_summary(self, session_id: str) -> ContextSummary | None:
        """获取指定会话的摘要。"""
        return self._sharing_manager.get_summary(session_id)

    def get_stale_sessions(self) -> list[str]:
        """获取需要更新摘要的会话列表。"""
        return self._injector.get_stale_sessions()