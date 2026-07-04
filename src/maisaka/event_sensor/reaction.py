"""事件-反应映射。

根据智能体人设和当前情绪对群事件做出个性化反应。
同一事件只反应一次。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from src.maisaka.agent.config import AgentConfig, EventReactionRule

from .sensor import GroupEvent, GroupEventType

logger = logging.getLogger(__name__)


@dataclass
class EventReaction:
    """事件反应。"""

    should_react: bool = False
    reaction_style: str = ""
    emotion_trigger: dict[str, int] = field(default_factory=dict)
    reason: str = ""


class EventReactionMapper:
    """事件-反应映射器。"""

    def __init__(self) -> None:
        self._reacted_events: set[str] = set()

    def map_reaction(
        self,
        event: GroupEvent,
        agent_config: AgentConfig,
        emotion_state: dict[str, int] | None = None,
    ) -> EventReaction:
        """根据事件和智能体配置决定反应。

        Args:
            event: 群事件。
            agent_config: 智能体配置。
            emotion_state: 当前情绪状态。

        Returns:
            EventReaction: 反应决策。
        """
        event_key = f"{event.group_id}:{event.event_type.value}:{event.user_id}:{event.timestamp:.0f}"
        if event_key in self._reacted_events:
            return EventReaction(reason="同一事件已反应过")

        matched_rule = self._find_matching_rule(event, agent_config.event_reaction_rules)

        if matched_rule is None:
            default_reaction = self._get_default_reaction(event, agent_config)
            if default_reaction.should_react:
                self._reacted_events.add(event_key)
            return default_reaction

        import random

        if random.random() > matched_rule.reaction_probability:
            return EventReaction(reason="概率判定不反应")

        self._reacted_events.add(event_key)

        return EventReaction(
            should_react=True,
            reaction_style=matched_rule.reaction_style,
            emotion_trigger=matched_rule.emotion_trigger,
            reason=f"匹配规则: {matched_rule.event_type}",
        )

    def _find_matching_rule(
        self,
        event: GroupEvent,
        rules: list[EventReactionRule],
    ) -> EventReactionRule | None:
        """查找匹配的事件反应规则。"""
        for rule in rules:
            if rule.event_type == event.event_type.value:
                return rule
            if rule.event_type == event.event_type.label:
                return rule
        return None

    def _get_default_reaction(
        self,
        event: GroupEvent,
        agent_config: AgentConfig,
    ) -> EventReaction:
        """获取默认反应。"""
        if event.event_type == GroupEventType.RED_PACKET:
            personality = agent_config.personality.lower()
            if any(kw in personality for kw in ["活泼", "调皮", "贪吃", "琪亚娜", "银狼"]):
                return EventReaction(
                    should_react=True,
                    reaction_style="抢红包",
                    emotion_trigger={"excited": 10, "happy": 5},
                    reason="性格匹配: 活泼型抢红包",
                )
            return EventReaction(reason="性格不匹配红包反应")

        if event.event_type == GroupEventType.POKE:
            return EventReaction(
                should_react=True,
                reaction_style="回应戳一戳",
                emotion_trigger={"happy": 5},
                reason="默认戳一戳反应",
            )

        if event.event_type in (GroupEventType.MEMBER_JOIN,):
            return EventReaction(
                should_react=True,
                reaction_style="欢迎入群",
                emotion_trigger={"happy": 3},
                reason="默认入群欢迎",
            )

        return EventReaction(reason=f"无默认反应: {event.event_type.value}")

    def clear_cache(self) -> None:
        """清理已反应事件缓存。"""
        self._reacted_events.clear()