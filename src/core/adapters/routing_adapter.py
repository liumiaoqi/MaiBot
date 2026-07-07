"""ChatManagerRoutingAdapter — AgentRoutingService 的 chat_manager 适配器。"""

from __future__ import annotations

from typing import Optional

from src.common.logger import get_logger
from src.core.protocols import AgentRoutingService
from src.maisaka.agent.config import AgentConfig

logger = get_logger("core.adapters.routing_adapter")


class ChatManagerRoutingAdapter:
    """通过 chat_manager._agent_router 实现 AgentRoutingService Protocol。"""

    def _ensure_router(self):
        from src.chat.message_receive.chat_manager import chat_manager

        return chat_manager.agent_router

    def resolve_agent(self, session_id: str, group_id: Optional[str] = None) -> AgentConfig:
        router = self._ensure_router()
        return router.resolve_agent(session_id, group_id)

    def bind_session(self, session_id: str, agent_id: str) -> bool:
        router = self._ensure_router()
        try:
            router.bind_session(session_id, agent_id)
            return True
        except ValueError:
            logger.warning(f"绑定失败: session={session_id}, agent={agent_id}")
            return False

    def unbind_session(self, session_id: str, agent_id: Optional[str] = None) -> None:
        router = self._ensure_router()
        router.unbind_session(session_id, agent_id)

    def get_primary_agent(self, session_id: str) -> Optional[str]:
        router = self._ensure_router()
        return router.get_session_primary_agent(session_id)

    def get_session_all_agents(self, session_id: str) -> frozenset[str]:
        router = self._ensure_router()
        return frozenset(router.get_session_all_agents(session_id))