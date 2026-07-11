from typing import TYPE_CHECKING, Dict, List, Optional

from rich.traceback import install

from src.common.logger import get_logger
from src.common.utils.utils_session import SessionUtils
from src.maisaka.agent.registry import AgentConfigRegistry
from src.maisaka.agent.router import AgentRouter

from .binding_restorer import BindingRestorer
from .message_registry import MessageRegistry
from .session_lifecycle import SessionLifecycle
from .session_name_cache import SessionNameCache
from .session_resolver import SessionResolver
from .session_store import SessionStore
from .session_types import BotChatSession, SessionContext

if TYPE_CHECKING:
    from .message import SessionMessage

install(extra_lines=3)

logger = get_logger("chat_manager")


class ChatManager:
    """薄协调层 — 持有子模块实例，对外暴露方法逐一委托。"""

    def __init__(self) -> None:
        self.session_store = SessionStore()
        self.message_registry = MessageRegistry(self.session_store)
        self.session_store.set_message_registry(self.message_registry)
        self.name_cache = SessionNameCache(self.session_store)
        self.resolver = SessionResolver(self.session_store)
        self._agent_router: Optional[AgentRouter] = None
        self.binding_restorer: Optional[BindingRestorer] = None
        self.session_lifecycle: Optional[SessionLifecycle] = None

    @property
    def sessions(self) -> Dict[str, BotChatSession]:
        """向后兼容属性代理。"""
        return self.session_store.sessions

    @property
    def last_messages(self) -> Dict[str, "SessionMessage"]:
        """向后兼容属性代理。"""
        return self.message_registry.last_messages

    @property
    def agent_router(self) -> AgentRouter:
        """获取智能体路由器单例，供外部模块访问"""
        return self._ensure_agent_router()

    def _ensure_agent_router(self) -> AgentRouter:
        """延迟初始化智能体路由器"""
        if self._agent_router is None:
            registry = AgentConfigRegistry()
            self._agent_router = AgentRouter(registry)
        return self._agent_router

    def _ensure_lifecycle(self) -> SessionLifecycle:
        """延迟初始化 SessionLifecycle（依赖 agent_router）。"""
        if self.session_lifecycle is None:
            self.session_lifecycle = SessionLifecycle(
                self.session_store,
                self.message_registry,
                self._ensure_agent_router(),
            )
        return self.session_lifecycle

    def _ensure_binding_restorer(self) -> BindingRestorer:
        """延迟初始化 BindingRestorer。"""
        if self.binding_restorer is None:
            self.binding_restorer = BindingRestorer(self._ensure_agent_router())
        return self.binding_restorer

    async def initialize(self):
        """初始化聊天管理器"""
        await self._ensure_lifecycle().initialize(self._ensure_binding_restorer())

    async def get_or_create_session(
        self,
        platform: str,
        user_id: str,
        group_id: Optional[str] = None,
        account_id: Optional[str] = None,
        scope: Optional[str] = None,
    ) -> BotChatSession:
        """获取会话，如果不存在则创建一个新会话。"""
        return await self._ensure_lifecycle().get_or_create_session(
            platform=platform,
            user_id=user_id,
            group_id=group_id,
            account_id=account_id,
            scope=scope,
        )

    def register_message(self, message: "SessionMessage"):
        self.message_registry.register(message)

    async def load_all_sessions_from_db(self):
        """从数据库加载全部会话记录到内存中"""
        self.session_store.sessions.clear()
        import asyncio
        try:
            await asyncio.to_thread(self.session_store.load_all_from_db)
        except Exception as e:
            logger.error(f"从数据库加载会话记录时发生错误: {e}")
            self.session_store.sessions.clear()
            raise e

    async def regularly_save_sessions(self, interval_seconds: int = 300):
        """定期将会话记录保存到数据库中"""
        await self._ensure_lifecycle().regularly_save_sessions(interval_seconds)

    def save_all_sessions(self):
        """将内存中的全部会话记录保存到数据库"""
        self._ensure_lifecycle().save_all_sessions()

    def get_session_name(self, session_id: str) -> Optional[str]:
        """根据会话ID获取会话名称"""
        return self.name_cache.get(session_id)

    def get_session_by_info(
        self,
        platform: str,
        user_id: Optional[str] = None,
        group_id: Optional[str] = None,
        account_id: Optional[str] = None,
        scope: Optional[str] = None,
    ) -> Optional[BotChatSession]:
        """根据平台、用户ID和群ID获取对应的会话"""
        session_id = SessionUtils.calculate_session_id(
            platform,
            user_id=user_id,
            group_id=group_id,
            account_id=account_id,
            scope=scope,
        )
        return self.get_session_by_session_id(session_id)

    def resolve_sessions_by_target(
        self,
        *,
        platform: str,
        target_id: str,
        chat_type: str,
    ) -> List[BotChatSession]:
        """按平台、目标 ID 与聊天类型解析已存在的真实聊天流。"""
        return self.resolver.resolve_by_target(platform=platform, target_id=target_id, chat_type=chat_type)

    def resolve_session_ids_by_target(
        self,
        *,
        platform: str,
        target_id: str,
        chat_type: str,
    ) -> set[str]:
        """按平台、目标 ID 与聊天类型解析已存在的真实聊天流 ID。"""
        return self.resolver.resolve_ids_by_target(platform=platform, target_id=target_id, chat_type=chat_type)

    def get_session_by_session_id(self, session_id: str) -> Optional[BotChatSession]:
        """根据会话ID获取对应的会话"""
        return self.session_store.get(session_id)

    def get_existing_session_by_session_id(self, session_id: str) -> Optional[BotChatSession]:
        """根据会话 ID 获取已存在的真实会话，内存未命中时从数据库加载。"""
        return self.session_store.get_existing(session_id)


chat_manager = ChatManager()
