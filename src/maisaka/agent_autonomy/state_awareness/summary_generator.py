"""共居状态摘要生成器——将共居智能体状态映射为自然语言摘要文本。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.common.logger import get_logger
from src.config.config import global_config
from src.maisaka.agent_autonomy.state_awareness.mapping import (
    EmotionTendencyMapping,
    VitalityLevel,
    VitalityLevelMapping,
)
from src.maisaka.agent_autonomy.state_awareness.visibility_rule import StateVisibilityRule

if TYPE_CHECKING:
    from src.maisaka.agent_autonomy.orchestrator import AgentOrchestrator
    from src.maisaka.agent_autonomy.vitality_manager import VitalityManager

logger = get_logger("agent_autonomy.summary_generator")

_MAX_SUMMARY_LENGTH = 500

_vitality_mapping = VitalityLevelMapping()
_emotion_mapping = EmotionTendencyMapping()


class CohabitantStateEntry:
    """共居智能体状态条目。"""

    def __init__(
        self,
        agent_id: str,
        display_name: str,
        state: str,
        vitality_level: VitalityLevel,
        emotion_tendency: str = "",
    ) -> None:
        self.agent_id = agent_id
        self.display_name = display_name
        self.state = state
        self.vitality_level = vitality_level
        self.emotion_tendency = emotion_tendency

    def to_description(self) -> str:
        """生成单条自然语言描述。"""
        desc = _vitality_mapping.map_to_description(self.vitality_level, self.state)
        parts = [f"{self.display_name}{desc}"]
        if self.emotion_tendency:
            parts.append(f"，{self.emotion_tendency}")
        return "".join(parts)


class CohabitantStateSummaryGenerator:
    """共居状态摘要生成器。"""

    def __init__(
        self,
        vitality_manager: VitalityManager,
        orchestrator: AgentOrchestrator,
        visibility_rule: StateVisibilityRule,
    ) -> None:
        self._vitality_manager = vitality_manager
        self._orchestrator = orchestrator
        self._visibility_rule = visibility_rule

    def generate(self, session_id: str, observer_agent_id: str) -> str:
        """生成共居状态摘要文本。"""
        if not global_config.agent_autonomy.state_awareness_enabled:
            return ""

        entries = self._build_entries(session_id, observer_agent_id)
        if not entries:
            return ""

        entries.sort(key=lambda e: (
            0 if e.state == "active" else 1,
            {VitalityLevel.HIGH: 0, VitalityLevel.MEDIUM: 1, VitalityLevel.LOW: 2}.get(e.vitality_level, 3),
        ))

        descriptions = [e.to_description() for e in entries]
        summary = "\n你身边的同伴状态：" + "；".join(descriptions)

        if len(summary) > _MAX_SUMMARY_LENGTH:
            summary = summary[:_MAX_SUMMARY_LENGTH]

        return summary

    def generate_preview(self, session_id: str) -> dict[str, Any]:
        """生成感知关系预览数据（供 WebUI 使用）。"""
        active_agents = self._orchestrator.get_active_agents()
        observer_ids = [a.agent_id for a in active_agents]

        all_entries: list[dict[str, Any]] = []
        summary_texts: dict[str, str] = {}

        for observer_id in observer_ids:
            entries = self._build_entries(session_id, observer_id)
            for e in entries:
                all_entries.append({
                    "agent_id": e.agent_id,
                    "display_name": e.display_name,
                    "state": e.state,
                    "vitality_level": e.vitality_level.value,
                    "emotion_tendency": e.emotion_tendency,
                    "observer_id": observer_id,
                })
            if entries:
                summary_texts[observer_id] = self.generate(session_id, observer_id)

        return {
            "observer_agents": observer_ids,
            "cohabitant_entries": all_entries,
            "summary_texts": summary_texts,
        }

    def _build_entries(
        self, session_id: str, observer_agent_id: str
    ) -> list[CohabitantStateEntry]:
        """构建共居智能体状态条目列表。"""
        entries: list[CohabitantStateEntry] = []

        # 活跃智能体
        for agent in self._orchestrator.get_active_agents():
            if agent.agent_id == observer_agent_id:
                continue
            vis = self._visibility_rule.evaluate("active", "active")
            if not vis.visible:
                continue

            display_name = self._get_display_name(agent.agent_id)
            emotion_tendency = ""

            if vis.show_emotion and agent.emotion_manager is not None:
                state = agent.emotion_manager.state
                emotion_tendency = _emotion_mapping.map_to_tendency(
                    state.dominant_emotion,
                    state.get_dominant_intensity(),
                )

            entries.append(CohabitantStateEntry(
                agent_id=agent.agent_id,
                display_name=display_name,
                state="active",
                vitality_level=VitalityLevel.HIGH,
                emotion_tendency=emotion_tendency,
            ))

        # 待命智能体
        for info in self._vitality_manager.get_standby_agents(session_id):
            if info.agent_id == observer_agent_id:
                continue
            vis = self._visibility_rule.evaluate("active", "standby")
            if not vis.visible:
                continue

            display_name = self._get_display_name(info.agent_id)
            vitality_level = _vitality_mapping.map_to_level(info.vitality_value)
            emotion_tendency = ""

            if vis.show_emotion:
                from src.maisaka.agent_autonomy.agent import AutonomousAgent
                agent = AutonomousAgent(info.agent_id)
                if agent.emotion_manager is not None:
                    state = agent.emotion_manager.state
                    emotion_tendency = _emotion_mapping.map_to_tendency(
                        state.dominant_emotion,
                        state.get_dominant_intensity(),
                    )

            entries.append(CohabitantStateEntry(
                agent_id=info.agent_id,
                display_name=display_name,
                state="standby",
                vitality_level=vitality_level,
                emotion_tendency=emotion_tendency,
            ))

        return entries

    def _get_display_name(self, agent_id: str) -> str:
        """获取智能体显示名称。"""
        from src.maisaka.agent.registry import AgentConfigRegistry
        registry = AgentConfigRegistry()
        agent = registry.get_agent(agent_id)
        return agent.display_name
