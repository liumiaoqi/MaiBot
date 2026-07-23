"""AgentConfigProviderAdapter — 将 AgentConfigRegistry 包装为 AgentConfigProvider Protocol。"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.maisaka.agent.config import AgentConfig
    from src.core.protocols import AgentConfigProvider

from src.common.logger import get_logger

logger = get_logger("core.adapters.agent_config_port")

_provider: AgentConfigProvider | None = None

def get_agent_config_provider() -> "AgentConfigProvider":
    """获取全局 AgentConfigProvider 实例。

    Raises:
        RuntimeError: 未注册时抛出。
    """
    if _provider is None:
        raise RuntimeError("AgentConfigProvider 未注册，请先调用 set_agent_config_provider()")
    return _provider

def set_agent_config_provider(provider: "AgentConfigProvider") -> None:
    """注册全局 AgentConfigProvider 实例。"""
    global _provider
    if _provider is not None:
        logger.warning("AgentConfigProvider 已注册，将被覆盖")
    _provider = provider

def reset_agent_config_provider() -> None:
    """重置全局实例（仅用于测试）。"""
    global _provider
    _provider = None

class AgentConfigProviderAdapter:
    """纯委托适配器，包裹 AgentConfigRegistry 实现 AgentConfigProvider Protocol。"""

    def __init__(self, registry: "AgentConfigProvider") -> None:
        self._registry = registry

    def get_agent(self, agent_id: str) -> "AgentConfig":
        return self._registry.get_agent(agent_id)

    def list_agents(self) -> "list[AgentConfig]":
        return self._registry.list_agents()

    def get_default_agent(self) -> "AgentConfig":
        return self._registry.get_default_agent()

    def has_agent(self, agent_id: str) -> bool:
        return self._registry.has_agent(agent_id)

    def reload(self) -> None:
        self._registry.reload()

    def reload_agent(self, agent_id: str) -> bool:
        return self._registry.reload_agent(agent_id)

    def load(self) -> None:
        self._registry.load()
