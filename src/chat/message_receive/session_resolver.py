from typing import TYPE_CHECKING, Dict, List

from sqlmodel import select

from src.common.database.database import get_db_session
from src.common.database.database_model import ChatSession
from src.common.logger import get_logger

from .session_types import BotChatSession

if TYPE_CHECKING:
    from .session_store import SessionStore

logger = get_logger("session_resolver")


class SessionResolver:
    """路由解析 — 按平台/目标匹配会话（含数据库懒加载）。"""

    def __init__(self, store: "SessionStore") -> None:
        self._store = store

    def resolve_by_target(
        self,
        *,
        platform: str,
        target_id: str,
        chat_type: str,
    ) -> List["BotChatSession"]:
        """按平台、目标 ID 与聊天类型解析已存在的真实聊天流。"""
        normalized_platform = str(platform or "").strip()
        normalized_target_id = str(target_id or "").strip()
        normalized_chat_type = str(chat_type or "").strip()
        if not normalized_platform or not normalized_target_id:
            return []

        if normalized_chat_type == "group":
            target_attr = "group_id"
        elif normalized_chat_type == "private":
            target_attr = "user_id"
        else:
            return []

        matched_sessions: Dict[str, "BotChatSession"] = {}
        for session in self._store.sessions.values():
            if self._session_matches_target(
                session,
                platform=normalized_platform,
                target_attr=target_attr,
                target_id=normalized_target_id,
            ):
                matched_sessions[session.session_id] = session

        try:
            with get_db_session() as db_session:
                statement = select(ChatSession).filter_by(platform=normalized_platform)
                for db_instance in db_session.exec(statement).all():
                    if str(getattr(db_instance, target_attr) or "").strip() != normalized_target_id:
                        continue
                    if db_instance.session_id in matched_sessions:
                        continue
                    session = BotChatSession.from_db_instance(db_instance)
                    self._store.sessions[session.session_id] = session
                    if (
                        self._store._message_registry
                        and session.session_id in self._store._message_registry.last_messages
                    ):
                        session.set_context(self._store._message_registry.last_messages[session.session_id])
                    matched_sessions[session.session_id] = session
        except Exception as e:
            logger.error(
                f"按目标解析聊天流失败: platform={normalized_platform} "
                f"target_id={normalized_target_id} chat_type={normalized_chat_type} error={e}"
            )

        return list(matched_sessions.values())

    def resolve_ids_by_target(
        self,
        *,
        platform: str,
        target_id: str,
        chat_type: str,
    ) -> set[str]:
        """按平台、目标 ID 与聊天类型解析已存在的真实聊天流 ID。"""
        return {
            session.session_id
            for session in self.resolve_by_target(
                platform=platform,
                target_id=target_id,
                chat_type=chat_type,
            )
        }

    @staticmethod
    def _session_matches_target(
        session: "BotChatSession",
        *,
        platform: str,
        target_attr: str,
        target_id: str,
    ) -> bool:
        return (
            str(session.platform or "").strip() == platform
            and str(getattr(session, target_attr) or "").strip() == target_id
        )