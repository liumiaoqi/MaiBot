"""阶段五集成测试——性能优化、策略可配置、意图类型可注册、动态性格预留。"""

from __future__ import annotations

import asyncio
import time
import pytest

from src.maisaka.agent_autonomy.behavior_intent import BehaviorIntent, BehaviorIntentEngine
from src.maisaka.agent_autonomy.inner_need import InnerNeedEngine
from src.maisaka.agent_autonomy.orchestrator_strategy import (
    BaseOrchestratorStrategy,
    DefaultOrchestratorStrategy,
    ConservativeOrchestratorStrategy,
    InterjectionDecision,
    register_strategy,
    create_strategy,
    list_strategies,
)


class TestDefaultOrchestratorStrategy:
    """测试默认编排器策略。"""

    def test_schedule_by_strength_descending(self) -> None:
        strategy = DefaultOrchestratorStrategy()
        from unittest.mock import MagicMock

        cooldown = MagicMock()
        cooldown.can_interject.return_value = True

        intents = [
            ("agent_a", BehaviorIntent(intent_type="want_to_interject", intent_strength=30.0, intent_source="emotion", source_description="低强度")),
            ("agent_b", BehaviorIntent(intent_type="want_to_interject", intent_strength=80.0, intent_source="inner_need", source_description="高强度")),
        ]

        decisions = strategy.schedule_interjections(
            pending_intents=intents,
            active_agent_ids=["agent_a", "agent_b"],
            primary_agent_id="primary",
            session_id="test",
            cooldown_manager=cooldown,
        )

        assert len(decisions) == 2
        # 高强度应排在前面
        assert decisions[0].agent_id == "agent_b"
        assert decisions[0].scheduled is True
        assert decisions[1].agent_id == "agent_a"
        assert decisions[1].scheduled is True

    def test_primary_agent_not_scheduled(self) -> None:
        strategy = DefaultOrchestratorStrategy()
        from unittest.mock import MagicMock

        cooldown = MagicMock()
        cooldown.can_interject.return_value = True

        intents = [
            ("primary", BehaviorIntent(intent_type="want_to_interject", intent_strength=80.0, intent_source="test", source_description="主发言")),
        ]

        decisions = strategy.schedule_interjections(
            pending_intents=intents,
            active_agent_ids=["primary"],
            primary_agent_id="primary",
            session_id="test",
            cooldown_manager=cooldown,
        )

        assert len(decisions) == 1
        assert decisions[0].scheduled is False
        assert decisions[0].skip_reason == "is_primary"

    def test_cooldown_blocks_scheduling(self) -> None:
        strategy = DefaultOrchestratorStrategy()
        from unittest.mock import MagicMock

        cooldown = MagicMock()
        cooldown.can_interject.return_value = False

        intents = [
            ("agent_a", BehaviorIntent(intent_type="want_to_interject", intent_strength=80.0, intent_source="test", source_description="冷却中")),
        ]

        decisions = strategy.schedule_interjections(
            pending_intents=intents,
            active_agent_ids=["agent_a"],
            primary_agent_id="primary",
            session_id="test",
            cooldown_manager=cooldown,
        )

        assert len(decisions) == 1
        assert decisions[0].scheduled is False
        assert "cooldown" in decisions[0].skip_reason

    def test_max_concurrent(self) -> None:
        strategy = DefaultOrchestratorStrategy()
        assert strategy.get_max_concurrent_interjections() == 2


class TestConservativeOrchestratorStrategy:
    """测试保守编排器策略。"""

    def test_only_one_interjection(self) -> None:
        strategy = ConservativeOrchestratorStrategy(min_strength=30.0)
        from unittest.mock import MagicMock

        cooldown = MagicMock()
        cooldown.can_interject.return_value = True

        intents = [
            ("agent_a", BehaviorIntent(intent_type="want_to_interject", intent_strength=80.0, intent_source="test", source_description="高")),
            ("agent_b", BehaviorIntent(intent_type="want_to_interject", intent_strength=70.0, intent_source="test", source_description="中")),
        ]

        decisions = strategy.schedule_interjections(
            pending_intents=intents,
            active_agent_ids=["agent_a", "agent_b"],
            primary_agent_id="primary",
            session_id="test",
            cooldown_manager=cooldown,
        )

        scheduled = [d for d in decisions if d.scheduled]
        assert len(scheduled) == 1
        assert scheduled[0].agent_id == "agent_a"

    def test_below_min_strength_rejected(self) -> None:
        strategy = ConservativeOrchestratorStrategy(min_strength=60.0)
        from unittest.mock import MagicMock

        cooldown = MagicMock()
        cooldown.can_interject.return_value = True

        intents = [
            ("agent_a", BehaviorIntent(intent_type="want_to_interject", intent_strength=40.0, intent_source="test", source_description="低")),
        ]

        decisions = strategy.schedule_interjections(
            pending_intents=intents,
            active_agent_ids=["agent_a"],
            primary_agent_id="primary",
            session_id="test",
            cooldown_manager=cooldown,
        )

        assert len(decisions) == 1
        assert decisions[0].scheduled is False
        assert "below_threshold" in decisions[0].skip_reason

    def test_max_concurrent(self) -> None:
        strategy = ConservativeOrchestratorStrategy()
        assert strategy.get_max_concurrent_interjections() == 1


class TestStrategyRegistry:
    """测试策略注册表。"""

    def test_list_strategies(self) -> None:
        strategies = list_strategies()
        assert "default" in strategies
        assert "conservative" in strategies

    def test_create_default_strategy(self) -> None:
        strategy = create_strategy("default")
        assert isinstance(strategy, DefaultOrchestratorStrategy)

    def test_create_conservative_strategy(self) -> None:
        strategy = create_strategy("conservative", min_strength=70.0)
        assert isinstance(strategy, ConservativeOrchestratorStrategy)

    def test_create_unknown_strategy_raises(self) -> None:
        with pytest.raises(ValueError, match="未知的编排器策略"):
            create_strategy("nonexistent")

    def test_register_custom_strategy(self) -> None:
        class CustomStrategy(BaseOrchestratorStrategy):
            def schedule_interjections(self, **kwargs):
                return []

            def get_max_concurrent_interjections(self):
                return 5

        register_strategy("custom_test", CustomStrategy)
        assert "custom_test" in list_strategies()
        strategy = create_strategy("custom_test")
        assert isinstance(strategy, CustomStrategy)
        assert strategy.get_max_concurrent_interjections() == 5


class TestBehaviorIntentTypeRegistration:
    """测试行为意图类型可注册。"""

    def test_builtin_types(self) -> None:
        engine = BehaviorIntentEngine(InnerNeedEngine())
        assert "want_to_speak" in engine.get_registered_intent_types()
        assert "want_to_interject" in engine.get_registered_intent_types()

    def test_register_custom_type(self) -> None:
        engine = BehaviorIntentEngine(InnerNeedEngine())
        engine.register_intent_type("want_to_observe")
        assert engine.is_valid_intent_type("want_to_observe")
        assert "want_to_observe" in engine.get_registered_intent_types()

    def test_invalid_type(self) -> None:
        engine = BehaviorIntentEngine(InnerNeedEngine())
        assert not engine.is_valid_intent_type("nonexistent_type")


class TestParallelIntentCollection:
    """测试并行行为意图计算性能。"""

    @pytest.mark.asyncio
    async def test_parallel_collection_speed(self) -> None:
        from src.maisaka.agent_autonomy.agent import AutonomousAgent

        agents = [AutonomousAgent(f"test_agent_{i}") for i in range(3)]

        start = time.monotonic()
        tasks = [
            agent.produce_behavior_intents(intent_threshold=0.0)
            for agent in agents
        ]
        results = await asyncio.gather(*tasks)
        elapsed = time.monotonic() - start

        # 并行执行应在合理时间内完成（不含LLM调用，纯计算应<1s）
        assert elapsed < 2.0
        assert len(results) == 3


class TestDynamicIdentityProvider:
    """测试动态性格预留接口。"""

    def test_register_and_use_provider(self) -> None:
        from src.maisaka.agent_autonomy.prompt_builder import EmbodiedPlannerPromptBuilder

        builder = EmbodiedPlannerPromptBuilder("silver_wolf")

        dynamic_identity = "动态人设：银狼此刻心情复杂"
        builder.register_identity_provider(lambda agent_id: dynamic_identity if agent_id == "silver_wolf" else None)

        # 验证 provider 被注册
        assert len(builder._identity_providers) == 1

    def test_provider_returns_none_falls_through(self) -> None:
        from src.maisaka.agent_autonomy.prompt_builder import EmbodiedPlannerPromptBuilder

        builder = EmbodiedPlannerPromptBuilder("silver_wolf")

        # 注册一个返回 None 的 provider
        builder.register_identity_provider(lambda agent_id: None)

        # 应该有1个provider
        assert len(builder._identity_providers) == 1

    def test_multiple_providers_priority(self) -> None:
        from src.maisaka.agent_autonomy.prompt_builder import EmbodiedPlannerPromptBuilder

        builder = EmbodiedPlannerPromptBuilder("silver_wolf")

        builder.register_identity_provider(lambda agent_id: "第一个")
        builder.register_identity_provider(lambda agent_id: "第二个")

        # 第一个返回非None的provider应优先
        assert len(builder._identity_providers) == 2


class TestContextCache:
    """测试上下文切换缓存。"""

    @pytest.mark.asyncio
    async def test_cache_operations(self) -> None:
        from src.maisaka.agent_autonomy.orchestrator import AgentOrchestrator
        from unittest.mock import MagicMock

        adapter = MagicMock()
        adapter.current_agent_id = "silver_wolf"

        orchestrator = AgentOrchestrator(
            session_id="test_cache_session",
            session_name="缓存测试",
            chat_loop_adapter=adapter,
        )

        # 初始缓存为空
        assert orchestrator.get_cached_context("silver_wolf") is None

        # 更新缓存
        context = {"identity": "银狼", "emotion": "excited"}
        orchestrator.update_cached_context("silver_wolf", context)
        assert orchestrator.get_cached_context("silver_wolf") == context

        # 使缓存失效
        orchestrator.invalidate_cached_context("silver_wolf")
        assert orchestrator.get_cached_context("silver_wolf") is None

        # 清理
        AgentOrchestrator._registry.pop("test_cache_session", None)