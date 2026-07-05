from __future__ import annotations

import logging
from typing import Optional

from .config import AgentConfig
from .registry import AgentConfigRegistry

logger = logging.getLogger(__name__)


class AgentRouter:
    """智能体路由层，管理会话与智能体的绑定关系。

    支持一个会话绑定多个智能体（共居模式），通过 _primary_order 记录绑定顺序，
    第一个绑定的智能体为主发言智能体。
    """

    def __init__(self, registry: AgentConfigRegistry) -> None:
        self._registry = registry
        self._session_bindings: dict[str, set[str]] = {}
        self._primary_order: dict[str, list[str]] = {}
        self._group_bindings: dict[str, str] = {}

    def _get_default_agent_id(self) -> str:
        """从配置获取默认智能体ID"""
        try:
            from src.config.config import global_config

            return global_config.agent.default_agent_id
        except Exception:
            return self._registry.get_default_agent().agent_id

    def resolve_agent(self, session_id: str, group_id: Optional[str] = None) -> AgentConfig:
        """解析会话应使用的智能体，优先级：会话绑定(主发言) → 群配置绑定 → 默认智能体"""
        primary = self.get_session_primary_agent(session_id)
        if primary is not None:
            if self._registry.has_agent(primary):
                return self._registry.get_agent(primary)
            logger.warning("会话绑定的主发言智能体不存在: session=%s, agent=%s", session_id, primary)

        if group_id is not None:
            agent_id = self._group_bindings.get(group_id)
            if agent_id is not None:
                if self._registry.has_agent(agent_id):
                    return self._registry.get_agent(agent_id)
                logger.warning("群绑定的智能体不存在: group=%s, agent=%s", group_id, agent_id)

        return self._registry.get_default_agent()

    def bind_session(self, session_id: str, agent_id: str) -> None:
        """绑定会话到指定智能体（支持多智能体共居）"""
        if not self._registry.has_agent(agent_id):
            raise ValueError(f"智能体不存在: {agent_id}")

        agents = self._session_bindings.setdefault(session_id, set())
        if agent_id in agents:
            logger.debug("会话已绑定该智能体，跳过: session=%s, agent=%s", session_id, agent_id)
            return

        agents.add(agent_id)
        order = self._primary_order.setdefault(session_id, [])
        order.append(agent_id)
        logger.info("会话绑定智能体: session=%s, agent=%s, 共居数=%d", session_id, agent_id, len(agents))

    def unbind_session(self, session_id: str, agent_id: Optional[str] = None) -> None:
        """解除会话的智能体绑定。

        agent_id=None 时清除该会话所有绑定；指定 agent_id 时仅移除该智能体。
        """
        if session_id not in self._session_bindings:
            return

        if agent_id is None:
            del self._session_bindings[session_id]
            self._primary_order.pop(session_id, None)
            logger.info("会话解除所有智能体绑定: session=%s", session_id)
            return

        agents = self._session_bindings[session_id]
        agents.discard(agent_id)

        order = self._primary_order.get(session_id, [])
        if agent_id in order:
            order.remove(agent_id)

        if not agents:
            del self._session_bindings[session_id]
            self._primary_order.pop(session_id, None)
            logger.info("会话最后一个智能体解绑，清除会话: session=%s", session_id)
        else:
            logger.info("会话解除单个智能体绑定: session=%s, agent=%s, 剩余=%d", session_id, agent_id, len(agents))

    def get_session_primary_agent(self, session_id: str) -> Optional[str]:
        """获取会话的主发言智能体ID"""
        order = self._primary_order.get(session_id, [])
        return order[0] if order else None

    def get_session_all_agents(self, session_id: str) -> set[str]:
        """获取会话绑定的所有智能体ID集合（副本）"""
        return set(self._session_bindings.get(session_id, set()))

    def get_session_binding(self, session_id: str) -> Optional[str]:
        """获取会话绑定的智能体ID（向后兼容，返回主发言智能体）"""
        return self.get_session_primary_agent(session_id)

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

    def get_group_binding(self, group_id: str) -> Optional[str]:
        """获取群绑定的智能体ID"""
        return self._group_bindings.get(group_id)

    def list_session_bindings(self) -> dict[str, set[str]]:
        """列出所有会话绑定（深拷贝）"""
        return {k: set(v) for k, v in self._session_bindings.items()}

    def list_group_bindings(self) -> dict[str, str]:
        """列出所有群绑定"""
        return dict(self._group_bindings)
