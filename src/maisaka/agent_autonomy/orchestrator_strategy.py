"""编排器策略——控制多智能体调度的核心决策逻辑。

策略只决定"如何调度"，不替智能体做决策。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from src.maisaka.agent_autonomy.behavior_intent import BehaviorIntent


class InterjectionDecision:
    """插话调度决策。"""

    __slots__ = ("agent_id", "intent", "scheduled", "skip_reason")

    def __init__(
        self,
        agent_id: str,
        intent: BehaviorIntent,
        scheduled: bool = True,
        skip_reason: str = "",
    ) -> None:
        self.agent_id = agent_id
        self.intent = intent
        self.scheduled = scheduled
        self.skip_reason = skip_reason


class BaseOrchestratorStrategy(ABC):
    """编排器策略基类。

    策略决定：
    1. 如何排序待处理的意图
    2. 哪些意图应该被调度执行
    3. 插话的最大并发数
    """

    @abstractmethod
    def schedule_interjections(
        self,
        pending_intents: list[tuple[str, BehaviorIntent]],
        active_agent_ids: list[str],
        primary_agent_id: str,
        session_id: str,
        cooldown_manager: Any,
    ) -> list[InterjectionDecision]:
        """根据策略调度插话。"""
        ...

    @abstractmethod
    def get_max_concurrent_interjections(self) -> int:
        """获取最大并发插话数。"""
        ...


class DefaultOrchestratorStrategy(BaseOrchestratorStrategy):
    """默认编排器策略——按意图强度降序排序，冷却+频率限制过滤。"""

    def schedule_interjections(
        self,
        pending_intents: list[tuple[str, BehaviorIntent]],
        active_agent_ids: list[str],
        primary_agent_id: str,
        session_id: str,
        cooldown_manager: Any,
    ) -> list[InterjectionDecision]:
        sorted_intents = sorted(
            pending_intents,
            key=lambda x: x[1].intent_strength,
            reverse=True,
        )

        decisions: list[InterjectionDecision] = []
        for agent_id, intent in sorted_intents:
            if agent_id not in active_agent_ids:
                decisions.append(InterjectionDecision(
                    agent_id=agent_id,
                    intent=intent,
                    scheduled=False,
                    skip_reason="agent_not_active",
                ))
                continue

            if agent_id == primary_agent_id:
                decisions.append(InterjectionDecision(
                    agent_id=agent_id,
                    intent=intent,
                    scheduled=False,
                    skip_reason="is_primary",
                ))
                continue

            if not cooldown_manager.can_interject(session_id, agent_id):
                decisions.append(InterjectionDecision(
                    agent_id=agent_id,
                    intent=intent,
                    scheduled=False,
                    skip_reason="cooldown_or_frequency_limit",
                ))
                continue

            decisions.append(InterjectionDecision(
                agent_id=agent_id,
                intent=intent,
                scheduled=True,
            ))

        return decisions

    def get_max_concurrent_interjections(self) -> int:
        return 2


class ConservativeOrchestratorStrategy(BaseOrchestratorStrategy):
    """保守策略——一次只允许一个插话，且强度阈值更高。"""

    def __init__(self, min_strength: float = 50.0) -> None:
        self._min_strength = min_strength

    def schedule_interjections(
        self,
        pending_intents: list[tuple[str, BehaviorIntent]],
        active_agent_ids: list[str],
        primary_agent_id: str,
        session_id: str,
        cooldown_manager: Any,
    ) -> list[InterjectionDecision]:
        sorted_intents = sorted(
            pending_intents,
            key=lambda x: x[1].intent_strength,
            reverse=True,
        )

        decisions: list[InterjectionDecision] = []
        scheduled_count = 0

        for agent_id, intent in sorted_intents:
            if intent.intent_strength < self._min_strength:
                decisions.append(InterjectionDecision(
                    agent_id=agent_id,
                    intent=intent,
                    scheduled=False,
                    skip_reason=f"below_threshold({intent.intent_strength:.1f}<{self._min_strength})",
                ))
                continue

            if agent_id not in active_agent_ids or agent_id == primary_agent_id:
                decisions.append(InterjectionDecision(
                    agent_id=agent_id,
                    intent=intent,
                    scheduled=False,
                    skip_reason="not_eligible",
                ))
                continue

            if not cooldown_manager.can_interject(session_id, agent_id):
                decisions.append(InterjectionDecision(
                    agent_id=agent_id,
                    intent=intent,
                    scheduled=False,
                    skip_reason="cooldown",
                ))
                continue

            if scheduled_count >= 1:
                decisions.append(InterjectionDecision(
                    agent_id=agent_id,
                    intent=intent,
                    scheduled=False,
                    skip_reason="max_concurrent_reached",
                ))
                continue

            decisions.append(InterjectionDecision(
                agent_id=agent_id,
                intent=intent,
                scheduled=True,
            ))
            scheduled_count += 1

        return decisions

    def get_max_concurrent_interjections(self) -> int:
        return 1


# 策略注册表
_STRATEGY_REGISTRY: dict[str, type[BaseOrchestratorStrategy]] = {
    "default": DefaultOrchestratorStrategy,
    "conservative": ConservativeOrchestratorStrategy,
}


def register_strategy(name: str, strategy_cls: type[BaseOrchestratorStrategy]) -> None:
    """注册自定义编排器策略。"""
    _STRATEGY_REGISTRY[name] = strategy_cls


def create_strategy(name: str, **kwargs: Any) -> BaseOrchestratorStrategy:
    """根据名称创建编排器策略实例。"""
    cls = _STRATEGY_REGISTRY.get(name)
    if cls is None:
        raise ValueError(f"未知的编排器策略: {name}，可用策略: {list(_STRATEGY_REGISTRY.keys())}")
    return cls(**kwargs)


def list_strategies() -> list[str]:
    """列出所有已注册的策略名称。"""
    return list(_STRATEGY_REGISTRY.keys())