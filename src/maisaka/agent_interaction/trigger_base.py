"""交互触发器基类与注册表。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from src.maisaka.agent.emotion import EmotionState
from src.maisaka.agent_interaction.models import AgentInteractionRelationshipRead


@dataclass
class TriggerEvaluation:
    """触发器评估结果。"""

    should_trigger: bool = False
    trigger_probability: float = 0.0
    initiator_agent_id: str = ""
    target_agent_id: str = ""
    interaction_type: str = ""
    trigger_reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseTrigger(ABC):
    """交互触发器抽象基类。

    所有触发器子类需实现 evaluate 方法，
    根据智能体的情绪、关系、记忆、时间等上下文判断是否应触发交互。
    """

    @abstractmethod
    async def evaluate(
        self,
        agent_id: str,
        emotion_state: EmotionState,
        relationships: list[AgentInteractionRelationshipRead],
        memory_context: dict[str, Any] | None = None,
        time_context: dict[str, Any] | None = None,
    ) -> TriggerEvaluation:
        """评估是否应触发交互。

        Args:
            agent_id: 发起方智能体ID
            emotion_state: 智能体当前情绪状态
            relationships: 智能体与其他智能体的关系列表
            memory_context: 记忆上下文（可选）
            time_context: 时间上下文（可选）

        Returns:
            TriggerEvaluation 触发评估结果
        """


class TriggerRegistry:
    """触发器注册表。

    管理所有已注册的触发器实例，支持按触发类型注册和查询。
    """

    def __init__(self) -> None:
        self._triggers: dict[str, BaseTrigger] = {}

    def register(self, trigger_type: str, trigger: BaseTrigger) -> None:
        self._triggers[trigger_type] = trigger

    def get(self, trigger_type: str) -> BaseTrigger | None:
        return self._triggers.get(trigger_type)

    def list_types(self) -> list[str]:
        return list(self._triggers.keys())

    def all_triggers(self) -> list[tuple[str, BaseTrigger]]:
        return list(self._triggers.items())