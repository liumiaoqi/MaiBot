from __future__ import annotations

import logging
from typing import Optional

from .config import AgentConfig
from .registry import AgentConfigRegistry

logger = logging.getLogger(__name__)


class AgentRouter:
    """智能体路由层，管理会话与智能体的绑定关系"""

    def __init__(self, registry: AgentConfigRegistry) -> None:
        self._registry = registry
        self._session_bindings: dict[str, str] = {}
        self._group_bindings: dict[str, str] = {}

    def resolve_agent(self, session_id: str, group_id: Optional[str] = None) -> AgentConfig:
        """解析会话应使用的智能体，优先级：会话绑定 → 群配置绑定 → 默认智能体"""
        agent_id = self._session_bindings.get(session_id)
        if agent_id is not None:
            if self._registry.has_agent(agent_id):
                return self._registry.get_agent(agent_id)
            logger.warning("会话绑定的智能体不存在: session=%s, agent=%s", session_id, agent_id)

        if group_id is not None:
            agent_id = self._group_bindings.get(group_id)
            if agent_id is not None:
                if self._registry.has_agent(agent_id):
                    return self._registry.get_agent(agent_id)
                logger.warning("群绑定的智能体不存在: group=%s, agent=%s", group_id, agent_id)

        return self._registry.get_default_agent()

    def bind_session(self, session_id: str, agent_id: str) -> None:
        """绑定会话到指定智能体"""
        if not self._registry.has_agent(agent_id):
            raise ValueError(f"智能体不存在: {agent_id}")
        self._session_bindings[session_id] = agent_id
        logger.info("会话绑定智能体: session=%s, agent=%s", session_id, agent_id)

    def unbind_session(self, session_id: str) -> None:
        """解除会话的智能体绑定"""
        if session_id in self._session_bindings:
            del self._session_bindings[session_id]
            logger.info("会话解除智能体绑定: session=%s", session_id)

    def bind_group(self, group_id: str, agent_id: str) -> None:
        """绑定群到指定智能体"""
        if not self._registry.has_agent(agent_id):
            raise ValueError(f"智能体不存在: {agent_id}")
        self._group_bindings[group_id] = agent_id
        logger.info("群绑定智能体: group=%s, agent=%s", group_id, agent_id)

    def unbind_group(self, group_id: str) -> None:
        """解除群的智能体绑定"""
        if group_id in self._group_bindings:
            del self._group_bindings[group_id]
            logger.info("群解除智能体绑定: group=%s", group_id)

    def get_session_binding(self, session_id: str) -> Optional[str]:
        """获取会话绑定的智能体ID"""
        return self._session_bindings.get(session_id)

    def get_group_binding(self, group_id: str) -> Optional[str]:
        """获取群绑定的智能体ID"""
        return self._group_bindings.get(group_id)

    def list_session_bindings(self) -> dict[str, str]:
        """列出所有会话绑定"""
        return dict(self._session_bindings)

    def list_group_bindings(self) -> dict[str, str]:
        """列出所有群绑定"""
        return dict(self._group_bindings)