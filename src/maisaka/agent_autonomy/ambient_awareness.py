"""环境感知处理器——待命智能体感知会话消息、提及和话题，不产生可见回复。"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from src.common.logger import get_logger
from src.config.config import global_config
from src.maisaka.agent_autonomy.event_bus import AgentSpeakEvent, SessionMessageEvent

if TYPE_CHECKING:
    from src.maisaka.agent_autonomy.state_awareness.rule_engine import StateAwareRuleEngine
    from src.maisaka.agent_autonomy.vitality_manager import VitalityManager

logger = get_logger("agent_autonomy.ambient_awareness")


class AmbientAwarenessProcessor:
    """环境感知处理器——纯规则计算，不调用 LLM。"""

    def __init__(
        self,
        vitality_manager: VitalityManager,
        rule_engine: StateAwareRuleEngine | None = None,
    ) -> None:
        self._vitality_manager = vitality_manager
        self._rule_engine = rule_engine
        self._config = global_config.agent_autonomy

    async def on_session_message(self, event: SessionMessageEvent) -> None:
        """处理会话消息事件。"""
        session_id = event.session_id
        content = event.content

        if not content or not session_id:
            return

        standby_agents = self._vitality_manager.get_standby_agents(session_id)
        if not standby_agents:
            return

        stimulus_message = self._config.vitality_stimulus_message
        stimulus_mention = self._config.vitality_stimulus_mention
        stimulus_topic = self._config.vitality_stimulus_topic

        for info in standby_agents:
            try:
                delta = stimulus_message

                # 检查提及
                if self.check_mention(content, info.agent_id):
                    delta += stimulus_mention
                    if self._rule_engine is not None and event.sender_type == "agent":
                        mention_bonus = self._rule_engine.evaluate_for_mention(
                            session_id, "agent"
                        )
                        delta += mention_bonus
                    # 即时跃迁检查
                    await self._vitality_manager.check_instant_activation(
                        info.agent_id, session_id
                    )
                    # 如果已跃迁，跳过后续
                    if self._vitality_manager.registry.get(info.agent_id, session_id) is None:
                        continue

                # 检查话题相关性
                matched = self.check_topic_relevance(content, info.agent_id)
                if matched:
                    delta += stimulus_topic

                self._vitality_manager.update_vitality(
                    info.agent_id, session_id, delta, "ambient_message"
                )
            except Exception as exc:
                logger.debug(
                    f"[ambient] 消息感知异常: agent={info.agent_id} error={exc}"
                )

    async def on_agent_speak(self, event: AgentSpeakEvent) -> None:
        """处理智能体发言事件（情绪感染）。"""
        session_id = event.session_id
        if not session_id:
            return

        standby_agents = self._vitality_manager.get_standby_agents(session_id)
        if not standby_agents:
            return

        # 仅强烈情绪触发感染
        if event.emotion_intensity < self._config.companion_emotion_infection_trigger:
            return

        for info in standby_agents:
            if info.agent_id == event.agent_id:
                continue
            try:
                from src.maisaka.agent_interaction.emotion_registry import AgentEmotionManagerRegistry

                emotion_mgr = AgentEmotionManagerRegistry().get_emotion_manager(info.agent_id)
                infection_strength = self._config.vitality_stimulus_mention
                if self._rule_engine is not None:
                    bonus = self._rule_engine.evaluate_for_infection(
                        session_id, event.emotion_intensity
                    )
                    infection_strength += bonus
                emotion_mgr.apply_trigger(event.emotion_type, infection_strength)
            except Exception as exc:
                logger.debug(
                    f"[ambient] 情绪感染异常: agent={info.agent_id} error={exc}"
                )

    def check_mention(self, content: str, agent_id: str) -> bool:
        """检查消息是否提及指定智能体（匹配 display_name）。"""
        if not content:
            return False

        from src.maisaka.agent.registry import AgentConfigRegistry

        registry = AgentConfigRegistry.get_instance()
        if registry is None:
            return False

        agent_config = registry.get_agent(agent_id)
        display_name = agent_config.display_name

        if display_name and display_name in content:
            return True

        id_as_name = agent_id.replace("_", " ")
        if id_as_name in content.lower():
            return True

        return False

    def check_topic_relevance(self, content: str, agent_id: str) -> list[str]:
        """检查消息与智能体 personality 的关键词匹配。"""
        if not content:
            return []

        from src.maisaka.agent.registry import AgentConfigRegistry

        registry = AgentConfigRegistry.get_instance()
        if registry is None:
            return []

        agent_config = registry.get_agent(agent_id)
        personality = agent_config.personality

        if not personality:
            return []

        matched: list[str] = []
        keywords = set(re.findall(r"[\u4e00-\u9fff]{2,4}", personality))
        for kw in keywords:
            if kw in content:
                matched.append(kw)

        return matched