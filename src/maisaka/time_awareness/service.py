"""时间感知服务。

整合时间上下文构建器和定时触发调度器。
支持智能体差异化时间行为（琪亚娜早起型、符华夜猫型）。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from src.maisaka.agent.config import AgentConfig, TimeTriggerRule

from .context_builder import TimeContext, TimeContextBuilder
from .scheduler import TimeTriggerScheduler, TriggerEvent

logger = logging.getLogger(__name__)


class TimeAwarenessService:
    """时间感知服务。"""

    def __init__(self) -> None:
        self._context_builder = TimeContextBuilder()
        self._scheduler = TimeTriggerScheduler()

    def get_time_context(self, agent_config: AgentConfig) -> TimeContext:
        """获取指定智能体的时间上下文。

        Args:
            agent_config: 智能体配置。

        Returns:
            TimeContext: 时间上下文。
        """
        profile = agent_config.time_behavior_profile
        return self._context_builder.build(
            morning_active=profile.morning_active_coefficient,
            afternoon_active=profile.afternoon_active_coefficient,
            evening_active=profile.evening_active_coefficient,
            night_active=profile.night_active_coefficient,
        )

    def check_time_triggers(self, agent_config: AgentConfig) -> list[TriggerEvent]:
        """检查指定智能体的时间触发规则。

        Args:
            agent_config: 智能体配置。

        Returns:
            触发事件列表。
        """
        rules = agent_config.time_behavior_profile.greeting_rules
        if not rules:
            return []
        return self._scheduler.check_triggers(rules)

    def build_time_prompt(self, agent_config: AgentConfig) -> str:
        """构建注入提示词的时间上下文文本。

        Args:
            agent_config: 智能体配置。

        Returns:
            时间上下文提示词文本。
        """
        ctx = self.get_time_context(agent_config)
        return ctx.to_prompt_text()

    def get_active_coefficient(self, agent_config: AgentConfig) -> float:
        """获取指定智能体当前时段的活跃系数。

        Args:
            agent_config: 智能体配置。

        Returns:
            活跃系数。
        """
        ctx = self.get_time_context(agent_config)
        return ctx.active_coefficient