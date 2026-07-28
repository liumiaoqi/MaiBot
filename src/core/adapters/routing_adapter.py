"""ChatManagerRoutingAdapter — AgentRoutingService 的 chat_manager 适配器。"""


from typing import Optional

from src.common.logger import get_logger
from src.core.protocols import AgentRoutingService
from src.maisaka.agent.config import AgentConfig

logger = get_logger("core.adapters.routing_adapter")


class ChatManagerRoutingAdapter:
    """通过构造注入 AgentRouter 实现 AgentRoutingService Protocol。"""

    def __init__(self, agent_router: Any = None) -> None:
        self._agent_router = agent_router

    def _ensure_router(self):
        if self._agent_router is None:
            raise RuntimeError("ChatManagerRoutingAdapter: agent_router 未注入")
        return self._agent_router

    def resolve_agent(self, session_id: str, group_id: Optional[str] = None) -> AgentConfig:
        return self._ensure_router().resolve_agent(session_id, group_id)

    def bind_session(self, session_id: str, agent_id: str) -> bool:
        try:
            self._ensure_router().bind_session(session_id, agent_id)
            return True
        except ValueError:
            logger.warning(f"绑定失败: session={session_id}, agent={agent_id}")
            return False

    def unbind_session(self, session_id: str, agent_id: Optional[str] = None) -> None:
        self._ensure_router().unbind_session(session_id, agent_id)

    def get_primary_agent(self, session_id: str) -> Optional[str]:
        return self._ensure_router().get_session_primary_agent(session_id)

    def get_session_all_agents(self, session_id: str) -> frozenset[str]:
        return frozenset(self._ensure_router().get_session_all_agents(session_id))

    def get_session_binding(self, session_id: str) -> Optional[str]:
        return self._ensure_router().get_session_binding(session_id)

    def list_group_bindings(self) -> dict[str, str]:
        return self._ensure_router().list_group_bindings()

    def bind_group(self, group_id: str, agent_id: str) -> None:
        self._ensure_router().bind_group(group_id, agent_id)

    def unbind_group(self, group_id: str) -> None:
        self._ensure_router().unbind_group(group_id)
