"""ChatManagerAdapter — 统一适配器，同时满足 5 个 Protocol。

合并 SessionRepository + SessionInfoPort + SessionLifecyclePort + SessionQueryPort + MessageRegistryPort，
替代 ChatManagerSessionRepository，消除 getattr，扩展 SessionInfo 新增字段。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.common.logger import get_logger
from src.core.protocols import (
    AgentRoutingService,
    MessageRegistryPort,
    SessionInfoPort,
    SessionLifecyclePort,
    SessionQueryPort,
    SessionRepository,
)
from src.core.types import SessionInfo
from src.platform_io.route_key_factory import RouteKeyFactory

logger = get_logger("core.adapters.chat_manager_adapter")


class ChatManagerAdapter:
    """通过 chat_manager 统一实现 5 个 Protocol。

    返回不可变 SessionInfo 快照，外部修改不影响内部状态。
    """

    def __init__(self, routing_service: AgentRoutingService) -> None:
        self._routing_service = routing_service

    def _ensure_chat_manager(self):
        from src.chat.message_receive.chat_manager import chat_manager

        return chat_manager

    def _build_session_info(self, session, chat_manager, session_id: str) -> SessionInfo:
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
            created_timestamp=session.created_timestamp,
            last_active_timestamp=session.last_active_timestamp,
            account_id=session.account_id or "",
            scope=session.scope or "",
            user_cardname=session.user_cardname or "",
        )

    # ── SessionRepository ──────────────────────────────────────────

    async def get_session(self, session_id: str) -> Optional[SessionInfo]:
        chat_manager = self._ensure_chat_manager()
        session = chat_manager.get_session_by_session_id(session_id)
        if session is None:
            return None
        return self._build_session_info(session, chat_manager, session_id)

    async def get_session_name(self, session_id: str) -> str:
        chat_manager = self._ensure_chat_manager()
        name = chat_manager.get_session_name(session_id)
        return name or session_id

    # ── SessionInfoPort ────────────────────────────────────────────

    def get_session_info(self, session_id: str) -> Optional[SessionInfo]:
        chat_manager = self._ensure_chat_manager()
        session = chat_manager.get_session_by_session_id(session_id)
        if session is None:
            return None
        return self._build_session_info(session, chat_manager, session_id)

    def get_existing_session_info(self, session_id: str) -> Optional[SessionInfo]:
        chat_manager = self._ensure_chat_manager()
        session = chat_manager.get_existing_session_by_session_id(session_id)
        if session is None:
            return None
        return self._build_session_info(session, chat_manager, session_id)

    # ── SessionLifecyclePort ───────────────────────────────────────

    async def get_or_create_session_id(
        self,
        platform: str,
        user_id: str = "",
        group_id: str = "",
        account_id: str = "",
        scope: str = "",
    ) -> str:
        chat_manager = self._ensure_chat_manager()
        session = await chat_manager.get_or_create_session(
            platform=platform,
            user_id=user_id,
            group_id=group_id or None,
            account_id=account_id or None,
            scope=scope or None,
        )
        return session.session_id

    def save_all_sessions(self) -> None:
        chat_manager = self._ensure_chat_manager()
        chat_manager.save_all_sessions()

    async def initialize(self) -> None:
        chat_manager = self._ensure_chat_manager()
        await chat_manager.initialize()

    async def regularly_save_sessions(self, interval_seconds: float = 300) -> None:
        chat_manager = self._ensure_chat_manager()
        await chat_manager.regularly_save_sessions(interval_seconds=int(interval_seconds))

    # ── SessionQueryPort ───────────────────────────────────────────

    def resolve_sessions_by_target(
        self,
        *,
        platform: str,
        target_id: str,
        chat_type: str,
    ) -> List[SessionInfo]:
        chat_manager = self._ensure_chat_manager()
        sessions = chat_manager.resolve_sessions_by_target(
            platform=platform,
            target_id=target_id,
            chat_type=chat_type,
        )
        return [
            self._build_session_info(session, chat_manager, session.session_id)
            for session in sessions
        ]

    def resolve_session_ids_by_target(
        self,
        *,
        platform: str,
        target_id: str,
        chat_type: str,
    ) -> set[str]:
        chat_manager = self._ensure_chat_manager()
        return chat_manager.resolve_session_ids_by_target(
            platform=platform,
            target_id=target_id,
            chat_type=chat_type,
        )

    def get_last_message(self, session_id: str) -> Any:
        chat_manager = self._ensure_chat_manager()
        return chat_manager.last_messages.get(session_id)

    def list_sessions(self) -> List[SessionInfo]:
        chat_manager = self._ensure_chat_manager()
        return [
            self._build_session_info(session, chat_manager, session.session_id)
            for session in chat_manager.sessions.values()
        ]

    def get_route_metadata(self, session_id: str) -> Dict[str, object]:
        chat_manager = self._ensure_chat_manager()
        session = chat_manager.get_session_by_session_id(session_id)
        if session is None:
            return {}

        metadata: Dict[str, object] = {}

        if session.account_id:
            metadata["account_id"] = session.account_id
        if session.scope:
            metadata["scope"] = session.scope

        if session.context is not None and session.context.message is not None:
            additional_config = session.context.message.message_info.additional_config
            if isinstance(additional_config, dict):
                for key in RouteKeyFactory.ACCOUNT_ID_KEYS:
                    if key in additional_config and key not in metadata:
                        metadata[key] = additional_config[key]
                for key in RouteKeyFactory.SCOPE_KEYS:
                    if key in additional_config and key not in metadata:
                        metadata[key] = additional_config[key]

        return metadata

    def get_session_count(self) -> int:
        chat_manager = self._ensure_chat_manager()
        return len(chat_manager.sessions)

    # ── MessageRegistryPort ────────────────────────────────────────

    def register_message(self, message: Any) -> None:
        chat_manager = self._ensure_chat_manager()
        chat_manager.register_message(message)