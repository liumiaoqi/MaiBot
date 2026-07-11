from typing import TYPE_CHECKING, Optional

import asyncio

from sqlmodel import select

from src.common.database.database import get_db_session
from src.common.database.database_model import ChatSession
from src.common.logger import get_logger
from src.common.utils.utils_session import SessionUtils
from src.maisaka.agent.router import AgentRouter

from .session_types import BotChatSession

if TYPE_CHECKING:
    from .binding_restorer import BindingRestorer
    from .message_registry import MessageRegistry
    from .session_store import SessionStore

logger = get_logger("session_lifecycle")


class SessionLifecycle:
    """会话生命周期 — 创建/获取 + 路由元数据 + 批量持久化 + 初始化。"""

    def __init__(
        self,
        store: "SessionStore",
        message_registry: "MessageRegistry",
        agent_router: AgentRouter,
    ) -> None:
        self._store = store
        self._registry = message_registry
        self._agent_router = agent_router

    async def get_or_create_session(
        self,
        platform: str,
        user_id: str,
        group_id: Optional[str] = None,
        account_id: Optional[str] = None,
        scope: Optional[str] = None,
    ) -> "BotChatSession":
        """获取会话，如果不存在则创建一个新会话。"""
        session_id = SessionUtils.calculate_session_id(
            platform,
            user_id=user_id,
            group_id=group_id,
            account_id=account_id,
            scope=scope,
        )
        if session := self._store.get(session_id):
            route_metadata_changed = self._apply_route_metadata(session, account_id=account_id, scope=scope)
            session.update_active_time()
            identity_changed = False
            if session_id in self._registry.last_messages:
                identity_changed = self._registry.update_session_identity(session, self._registry.last_messages[session_id])
            if route_metadata_changed or identity_changed:
                self._store.save(session)
            return session

        # 内存没有就找db
        try:
            with get_db_session() as db_session:
                statement = select(ChatSession).filter_by(session_id=session_id).limit(1)
                if result := db_session.exec(statement).first():
                    session = BotChatSession.from_db_instance(result)
                    route_metadata_changed = self._apply_route_metadata(session, account_id=account_id, scope=scope)
                    identity_changed = False
                    if session.session_id in self._registry.last_messages:
                        session.set_context(self._registry.last_messages[session.session_id])
                        identity_changed = self._registry.update_session_identity(session, self._registry.last_messages[session.session_id])
                    if route_metadata_changed or identity_changed:
                        result.account_id = session.account_id
                        result.scope = session.scope
                        result.user_id = session.user_id
                        result.user_nickname = session.user_nickname
                        result.user_cardname = session.user_cardname
                        result.group_id = session.group_id
                        result.group_name = session.group_name
                        db_session.add(result)
                    self._store.sessions[session.session_id] = session
                    return session
        except Exception as e:
            logger.error(f"从数据库获取会话时发生错误: {e}")
            raise e

        # 都没有就创建新的
        agent_id = self._agent_router.resolve_agent(
            session_id=session_id,
            group_id=group_id,
        ).agent_id
        new_session = BotChatSession(
            session_id=session_id,
            platform=platform,
            user_id=user_id,
            group_id=group_id,
            account_id=account_id,
            scope=scope,
            agent_id=agent_id,
        )
        self._store.sessions[new_session.session_id] = new_session
        if new_session.session_id in self._registry.last_messages:
            new_session.set_context(self._registry.last_messages[new_session.session_id])
            self._registry.update_session_identity(new_session, self._registry.last_messages[new_session.session_id])
        self._store.save(new_session)
        return new_session

    async def initialize(self, binding_restorer: "BindingRestorer") -> None:
        """加载全部会话 + 恢复绑定。"""
        try:
            self._store.sessions.clear()
            await asyncio.to_thread(self._store.load_all_from_db)
            logger.debug(f"已加载 {len(self._store.sessions)} 个会话记录到内存中")
        except Exception as e:
            logger.error(f"初始化聊天管理器出现错误: {e}")

        binding_restorer.restore_bindings()
        binding_restorer.restore_orchestrator()

    def save_all_sessions(self) -> None:
        """将内存中的全部会话记录保存到数据库"""
        try:
            for session in self._store.sessions.values():
                self._store.save(session)
            logger.info(f"共 {len(self._store.sessions)} 个会话已经保存到数据库中")
        except Exception as e:
            logger.error(f"保存会话记录到数据库时发生错误: {e}")
            raise e

    async def regularly_save_sessions(self, interval_seconds: int = 300) -> None:
        """定期将会话记录保存到数据库中"""
        while True:
            await asyncio.sleep(interval_seconds)
            try:
                await asyncio.to_thread(self.save_all_sessions)
            except Exception as e:
                logger.error(f"定期保存会话记录时发生错误: {e}")

    @staticmethod
    def _normalize_route_value(value: Optional[str]) -> Optional[str]:
        normalized_value = str(value or "").strip()
        return normalized_value or None

    @classmethod
    def _apply_route_metadata(
        cls,
        session: "BotChatSession",
        *,
        account_id: Optional[str],
        scope: Optional[str],
    ) -> bool:
        changed = False
        normalized_account_id = cls._normalize_route_value(account_id)
        normalized_scope = cls._normalize_route_value(scope)

        if normalized_account_id and not cls._normalize_route_value(session.account_id):
            session.account_id = normalized_account_id
            changed = True
        if normalized_scope and not cls._normalize_route_value(session.scope):
            session.scope = normalized_scope
            changed = True
        return changed