"""智能体交互活化系统引导模块。

根据配置组装完整的调度链：
InteractionScheduler → InteractionTrigger → 6个触发器
                       → InteractionEngine → EffectCalculator
                       → AgentEmotionManagerRegistry
                       → AgentRelationshipManager
                       → InteractionCooldownManager
                       → InteractionEventStore
                       → AgentMemoryAdapter
                       → MonologueEngine
"""

from __future__ import annotations

import logging

from src.config.config import global_config
from src.maisaka.agent_interaction.cooldown import InteractionCooldownManager
from src.maisaka.agent_interaction.emotion_registry import AgentEmotionManagerRegistry
from src.maisaka.agent_interaction.engine import InteractionEngine
from src.maisaka.agent_interaction.event_store import InteractionEventStore
from src.maisaka.agent_interaction.memory.adapter import AgentMemoryAdapter
from src.maisaka.agent_interaction.monologue_engine import MonologueEngine
from src.maisaka.agent_interaction.monologue_trigger import MonologueTrigger
from src.maisaka.agent_interaction.relationship_manager import AgentRelationshipManager
from src.maisaka.agent_interaction.scheduler import InteractionScheduler
from src.maisaka.agent_interaction.trigger_base import TriggerRegistry
from src.maisaka.agent_interaction.trigger_scheduler import InteractionTrigger
from src.maisaka.agent_interaction.triggers import (
    EmotionDrivenTrigger,
    EventRippleTrigger,
    InnerNeedTrigger,
    MentionPropagationTrigger,
    MemoryDrivenTrigger,
    TimeAwarenessTrigger,
)

logger = logging.getLogger(__name__)


def build_interaction_scheduler() -> InteractionScheduler | None:
    """根据配置组装并返回 InteractionScheduler 实例。

    若 agent_interaction.enabled 为 False，返回 None。
    """
    cfg = global_config.agent_interaction

    if not cfg.enabled:
        logger.info("[agent_interaction] 智能体交互未启用，跳过调度器构建")
        return None

    # 基础组件
    emotion_registry = AgentEmotionManagerRegistry()
    relationship_manager = AgentRelationshipManager()
    cooldown_manager = InteractionCooldownManager()
    event_store = InteractionEventStore()
    memory_adapter = AgentMemoryAdapter()

    # 注册触发器
    trigger_registry = TriggerRegistry()
    trigger_registry.register("emotion_driven", EmotionDrivenTrigger())
    trigger_registry.register("time_awareness", TimeAwarenessTrigger())
    trigger_registry.register("mention_propagation", MentionPropagationTrigger())
    trigger_registry.register("event_ripple", EventRippleTrigger())
    trigger_registry.register("inner_need", InnerNeedTrigger())
    trigger_registry.register("memory_driven", MemoryDrivenTrigger(memory_adapter))

    # 交互引擎
    engine = InteractionEngine(
        emotion_registry=emotion_registry,
        relationship_manager=relationship_manager,
        event_store=event_store,
        memory_adapter=memory_adapter,
        echo_decay_ratio=cfg.echo_decay_ratio,
        echo_max_depth=cfg.echo_max_depth,
    )

    # 交互触发器调度器
    interaction_trigger = InteractionTrigger(
        emotion_registry=emotion_registry,
        relationship_manager=relationship_manager,
        engine=engine,
        cooldown_manager=cooldown_manager,
        trigger_registry=trigger_registry,
    )

    # 定时调度器
    scheduler = InteractionScheduler(
        trigger=interaction_trigger,
        evaluation_interval_seconds=cfg.evaluation_interval_seconds,
    )

    logger.info(
        "[agent_interaction] 调度器构建完成: interval=%ds, cooldown=%dm, echo=%s",
        cfg.evaluation_interval_seconds,
        cfg.cooldown_minutes,
        cfg.echo_enabled,
    )

    return scheduler


def build_monologue_engine() -> MonologueEngine | None:
    """根据配置组装并返回 MonologueEngine 实例。

    若 agent_interaction.monologue_enabled 为 False，返回 None。
    """
    cfg = global_config.agent_interaction

    if not cfg.enabled or not cfg.monologue_enabled:
        return None

    emotion_registry = AgentEmotionManagerRegistry()
    monologue_trigger = MonologueTrigger(
        idle_threshold_minutes=cfg.monologue_idle_threshold_minutes,
        emotion_intensity_threshold=cfg.monologue_emotion_intensity_threshold,
        min_interval_minutes=cfg.monologue_min_interval_minutes,
    )
    memory_adapter = AgentMemoryAdapter()

    return MonologueEngine(
        emotion_registry=emotion_registry,
        monologue_trigger=monologue_trigger,
        memory_adapter=memory_adapter,
    )