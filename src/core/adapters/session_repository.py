"""ChatManagerSessionRepository — SessionRepository 的 chat_manager 适配器。"""

from __future__ import annotations

from typing import Optional

from src.common.logger import get_logger
from src.core.protocols import AgentRoutingService, SessionRepository
from src.core.types import SessionInfo

logger = get_logger("core.adapters.session_repository")


class ChatManagerSessionRepository:
    """通过 chat_manager 实现 SessionRepository Protocol。

    返回不可变 SessionInfo 快照，外部修改不影响内部状态。
    """

    def __init__(self, routing_service: AgentRoutingService) -> None:
        self._routing_service = routing_service

    def _ensure_chat_manager(self):
        from src.chat.message_receive.chat_manager import chat_manager

        return chat_manager

    async def get_session(self, session_id: str) -> Optional[SessionInfo]:
        chat_manager = self._ensure_chat_manager()
        session = chat_manager.get_session_by_session_id(session_id)
        if session is None:
            return None

        primary_agent_id = self._routing_service.get_primary_agent(session_id) or ""
        cohabitant_ids = self._routing_service.get_session_all_agents(session_id) - {primary_agent_id}

        return SessionInfo(
            session_id=session.session_id,
            session_name=chat_manager.get_session_name(session_id) or session.session_id,
            platform=session.platform,
            is_group_session=session.is_group_session,
            group_id=session.group_id or "",
            group_name=session.group_name or "",
            user_id=session.user_id or "",
            user_nickname=session.user_nickname or "",
            primary_agent_id=primary_agent_id,
            cohabitant_agent_ids=cohabitant_ids,
        )

    async def get_session_name(self, session_id: str) -> str:
        chat_manager = self._ensure_chat_manager()
        name = chat_manager.get_session_name(session_id)
        return name or session_id