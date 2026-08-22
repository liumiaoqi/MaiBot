"""agent_interaction 核心 9 模块生产装配路径测试（P0-A11a-1）。

通过 bootstrap.build_interaction_scheduler() 装配完整调度链，
验证各组件实例化 + 功能可达（非自 init 自测，走生产路径）。
"""


from src.maisaka.agent_interaction.cooldown import InteractionCooldownManager
from src.maisaka.agent_interaction.effect_calculator import EffectCalculator
from src.maisaka.agent_interaction.emotion_registry import AgentEmotionManagerRegistry
from src.maisaka.agent_interaction.engine import InteractionEngine
from src.maisaka.agent_interaction.event_store import InteractionEventStore
from src.maisaka.agent_interaction.bootstrap import (
    build_interaction_scheduler,
    get_interaction_engine,
)
from src.maisaka.agent_interaction.relationship_manager import AgentRelationshipManager
from src.maisaka.agent_interaction.scheduler import InteractionScheduler
from src.maisaka.agent_interaction.trigger_base import TriggerRegistry
from src.maisaka.agent_interaction.trigger_scheduler import InteractionTrigger


class TestBootstrapWiring:
    """9 模块生产装配路径验证。"""

    def test_scheduler_instantiated(
        self, mock_app_config_port, mock_agent_config_provider, mock_memory_port
    ):
        """InteractionScheduler 通过 bootstrap 装配实例化。"""
        scheduler = build_interaction_scheduler(mock_memory_port)
        assert isinstance(scheduler, InteractionScheduler)

    def test_trigger_instantiated(
        self, mock_app_config_port, mock_agent_config_provider, mock_memory_port
    ):
        """InteractionTrigger 通过 bootstrap 装配实例化。"""
        scheduler = build_interaction_scheduler(mock_memory_port)
        assert isinstance(scheduler._trigger, InteractionTrigger)

    def test_engine_instantiated(
        self, mock_app_config_port, mock_agent_config_provider, mock_memory_port
    ):
        """InteractionEngine 通过 bootstrap 装配实例化。"""
        build_interaction_scheduler(mock_memory_port)
        engine = get_interaction_engine()
        assert isinstance(engine, InteractionEngine)

    def test_trigger_registry_instantiated(
        self, mock_app_config_port, mock_agent_config_provider, mock_memory_port
    ):
        """TriggerRegistry 通过 bootstrap 装配实例化。"""
        scheduler = build_interaction_scheduler(mock_memory_port)
        assert isinstance(scheduler._trigger._trigger_registry, TriggerRegistry)

    def test_cooldown_manager_instantiated(
        self, mock_app_config_port, mock_agent_config_provider, mock_memory_port
    ):
        """InteractionCooldownManager 通过 bootstrap 装配实例化。"""
        scheduler = build_interaction_scheduler(mock_memory_port)
        assert isinstance(scheduler._trigger._cooldown_manager, InteractionCooldownManager)

    def test_emotion_registry_instantiated(
        self, mock_app_config_port, mock_agent_config_provider, mock_memory_port
    ):
        """AgentEmotionManagerRegistry 通过 bootstrap 装配实例化。"""
        build_interaction_scheduler(mock_memory_port)
        engine = get_interaction_engine()
        assert isinstance(engine._emotion_registry, AgentEmotionManagerRegistry)

    def test_relationship_manager_instantiated(
        self, mock_app_config_port, mock_agent_config_provider, mock_memory_port
    ):
        """AgentRelationshipManager 通过 bootstrap 装配实例化。"""
        build_interaction_scheduler(mock_memory_port)
        engine = get_interaction_engine()
        assert isinstance(engine._relationship_manager, AgentRelationshipManager)

    def test_event_store_instantiated(
        self, mock_app_config_port, mock_agent_config_provider, mock_memory_port
    ):
        """InteractionEventStore 通过 bootstrap 装配实例化。"""
        build_interaction_scheduler(mock_memory_port)
        engine = get_interaction_engine()
        assert isinstance(engine._event_store, InteractionEventStore)

    def test_effect_calculator_instantiated(
        self, mock_app_config_port, mock_agent_config_provider, mock_memory_port
    ):
        """EffectCalculator 通过 bootstrap 装配实例化。"""
        build_interaction_scheduler(mock_memory_port)
        engine = get_interaction_engine()
        assert isinstance(engine._effect_calculator, EffectCalculator)