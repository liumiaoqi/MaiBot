from __future__ import annotations

import logging
from typing import Optional

from .config import AgentConfig
from .config_loader import AgentConfigLoader

logger = logging.getLogger(__name__)


class AgentConfigRegistry:
    """智能体配置注册表，管理所有已加载的智能体配置"""

    _instance: Optional["AgentConfigRegistry"] = None

    def __init__(self, config_dir: Optional[str] = None) -> None:
        if config_dir is None:
            try:
                from src.config.config import global_config

                config_dir = global_config.agent.agents_dir
            except Exception:
                config_dir = "agents/"
        self._loader = AgentConfigLoader(config_dir)
        self._agents: dict[str, AgentConfig] = {}
        self._default_agent: Optional[AgentConfig] = None
        self._loaded = False

    @classmethod
    def get_instance(cls) -> "AgentConfigRegistry":
        """获取全局单例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def load(self) -> None:
        """加载所有智能体配置"""
        self._agents = self._loader.load_all()
        self._default_agent = None

        for config in self._agents.values():
            if config.is_default:
                if self._default_agent is not None:
                    logger.warning(
                        "多个默认智能体: %s 和 %s，使用第一个",
                        self._default_agent.agent_id,
                        config.agent_id,
                    )
                else:
                    self._default_agent = config

        if self._default_agent is None and self._agents:
            first = next(iter(self._agents.values()))
            logger.warning("未设置默认智能体，使用第一个: %s", first.agent_id)
            self._default_agent = first

        self._loaded = True
        logger.info("已加载 %d 个智能体配置，默认: %s", len(self._agents), self._default_agent.agent_id if self._default_agent else "无")

    def get_agent(self, agent_id: str) -> AgentConfig:
        """获取指定智能体配置，不存在时返回默认智能体"""
        if not self._loaded:
            self.load()

        agent = self._agents.get(agent_id)
        if agent is not None:
            return agent

        logger.warning("智能体不存在: %s，回退到默认智能体", agent_id)
        if self._default_agent is not None:
            return self._default_agent

        return AgentConfig()

    def list_agents(self) -> list[AgentConfig]:
        """列出所有智能体配置"""
        if not self._loaded:
            self.load()
        return list(self._agents.values())

    def get_default_agent(self) -> AgentConfig:
        """获取默认智能体配置"""
        if not self._loaded:
            self.load()
        if self._default_agent is not None:
            return self._default_agent
        return AgentConfig()

    def reload(self) -> None:
        """重新加载所有智能体配置"""
        self._agents = self._loader.reload_all()
        self._default_agent = None
        self._loaded = False
        self.load()

    def has_agent(self, agent_id: str) -> bool:
        """检查智能体是否存在"""
        if not self._loaded:
            self.load()
        return agent_id in self._agents

    def reload_agent(self, agent_id: str) -> bool:
        """重新加载指定智能体配置，不影响其他智能体"""
        if agent_id not in self._agents:
            logger.warning("智能体不存在，无法重载: %s", agent_id)
            return False
        config = self._loader.reload(agent_id)
        if config is None:
            logger.warning("智能体重载失败: %s", agent_id)
            return False
        self._agents[agent_id] = config
        logger.info("智能体配置已重载: %s", agent_id)
        return True