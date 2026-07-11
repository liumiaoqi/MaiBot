from typing import TYPE_CHECKING, Dict, Iterable, Optional

from sqlmodel import select

from src.common.database.database import get_db_session
from src.common.database.database_model import ChatSession
from src.common.logger import get_logger

from .session_types import BotChatSession

if TYPE_CHECKING:
    from .message import SessionMessage
    from .message_registry import MessageRegistry

logger = get_logger("session_store")


class SessionStore:
    """会话存储 — 管理 sessions 字典的 CRUD + 单条持久化。"""

    def __init__(self) -> None:
        self.sessions: Dict[str, "BotChatSession"] = {}
        self._message_registry: Optional["MessageRegistry"] = None

    def set_message_registry(self, registry: "MessageRegistry") -> None:
        """延迟注入 MessageRegistry，避免循环依赖。"""
        self._message_registry = registry

    def get(self, session_id: str) -> Optional["BotChatSession"]:
        """查询会话，自动设置 context（从 last_messages）。"""
        session = self.sessions.get(session_id)
        if session and self._message_registry:
            last_msg = self._message_registry.get_last(session_id)
            if last_msg:
                session.set_context(last_msg)
        return session

    def get_existing(self, session_id: str) -> Optional["BotChatSession"]:
        """内存未命中时从数据库加载。"""
        normalized_session_id = str(session_id or "").strip()
        if not normalized_session_id:
            return None

        if session := self.get(normalized_session_id):
            return session

        try:
            with get_db_session() as db_session:
                statement = select(ChatSession).filter_by(session_id=normalized_session_id).limit(1)
                db_instance = db_session.exec(statement).first()
                if db_instance is None:
                    return None
                session = BotChatSession.from_db_instance(db_instance)
                self.sessions[session.session_id] = session
                if session.session_id in self._message_registry.last_messages if self._message_registry else False:
                    session.set_context(self._message_registry.last_messages[session.session_id])
                return session
        except Exception as e:
            logger.error(f"从数据库获取已有会话失败: session_id={normalized_session_id} error={e}")
            return None

    def add(self, session: "BotChatSession") -> None:
        """添加会话到存储。"""
        self.sessions[session.session_id] = session

    def remove(self, session_id: str) -> Optional["BotChatSession"]:
        """移除并返回会话，不存在则返回 None。"""
        return self.sessions.pop(session_id, None)

    def values(self) -> Iterable["BotChatSession"]:
        return self.sessions.values()

    def __len__(self) -> int:
        return len(self.sessions)

    def __contains__(self, session_id: str) -> bool:
        return session_id in self.sessions

    def save(self, session: "BotChatSession") -> None:
        """单条会话持久化（原 _save_session）。"""
        with get_db_session() as db_session:
            db_instance = session.to_db_instance()
            statement = select(ChatSession).filter_by(session_id=db_instance.session_id).limit(1)
            if result := db_session.exec(statement).first():
                result.created_timestamp = db_instance.created_timestamp
                result.last_active_timestamp = db_instance.last_active_timestamp
                result.user_id = db_instance.user_id
                result.user_nickname = db_instance.user_nickname
                result.user_cardname = db_instance.user_cardname
                result.group_id = db_instance.group_id
                result.group_name = db_instance.group_name
                result.account_id = db_instance.account_id
                result.scope = db_instance.scope
                result.agent_id = db_instance.agent_id
                db_session.add(result)
            else:
                db_session.add(db_instance)

    def load_all_from_db(self) -> None:
        """从数据库加载全部会话记录到内存中。"""
        with get_db_session() as db_session:
            statements = select(ChatSession)
            for model_instance in db_session.exec(statements).all():
                bot_chat_session = BotChatSession.from_db_instance(model_instance)
                self.sessions[bot_chat_session.session_id] = bot_chat_session
                if (
                    self._message_registry
                    and bot_chat_session.session_id in self._message_registry.last_messages
                ):
                    bot_chat_session.set_context(self._message_registry.last_messages[bot_chat_session.session_id])