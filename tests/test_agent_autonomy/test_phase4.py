"""阶段四集成测试——交互联动、插话反哺、行为意图持久化、结构化日志、WebUI API。"""

from __future__ import annotations

import asyncio
import pytest

from src.maisaka.agent_autonomy.event_bus import AutonomyEventBus, InteractionSignalEvent, InterjectionMentionEvent
from src.maisaka.agent_autonomy.behavior_intent import BehaviorIntent


class TestAutonomyEventBus:
    """测试自主性事件总线。"""

    def setup_method(self) -> None:
        self.bus = AutonomyEventBus()
        self.received: list[object] = []

    async def _handler(self, event: object) -> None:
        self.received.append(event)

    @pytest.mark.asyncio
    async def test_subscribe_and_emit(self) -> None:
        self.bus.subscribe("test_event", self._handler)
        await self.bus.emit("test_event", {"key": "value"})
        assert len(self.received) == 1

    @pytest.mark.asyncio
    async def test_unsubscribe(self) -> None:
        self.bus.subscribe("test_event", self._handler)
        self.bus.unsubscribe("test_event", self._handler)
        await self.bus.emit("test_event", {"key": "value"})
        assert len(self.received) == 0

    @pytest.mark.asyncio
    async def test_multiple_handlers(self) -> None:
        received2: list[object] = []

        async def handler2(event: object) -> None:
            received2.append(event)

        self.bus.subscribe("test_event", self._handler)
        self.bus.subscribe("test_event", handler2)
        await self.bus.emit("test_event", {"key": "value"})
        assert len(self.received) == 1
        assert len(received2) == 1

    @pytest.mark.asyncio
    async def test_handler_exception_does_not_block(self) -> None:
        async def bad_handler(event: object) -> None:
            raise RuntimeError("test error")

        self.bus.subscribe("test_event", bad_handler)
        self.bus.subscribe("test_event", self._handler)
        await self.bus.emit("test_event", {"key": "value"})
        assert len(self.received) == 1

    @pytest.mark.asyncio
    async def test_no_handlers(self) -> None:
        await self.bus.emit("unknown_event", {"key": "value"})
        assert len(self.received) == 0

    def test_emit_sync(self) -> None:
        self.bus.subscribe("sync_event", self._handler)
        self.bus.emit_sync("sync_event", {"key": "value"})

    def test_singleton(self) -> None:
        inst1 = AutonomyEventBus.get_instance()
        inst2 = AutonomyEventBus.get_instance()
        assert inst1 is inst2


class TestInteractionSignalEvent:
    """测试交互信号事件数据结构。"""

    def test_create_event(self) -> None:
        event = InteractionSignalEvent(
            initiator_agent_id="silver_wolf",
            target_agent_id="march_7th",
            interaction_type="mention_propagation",
            trigger_reason="银狼想念三月七",
        )
        assert event.initiator_agent_id == "silver_wolf"
        assert event.target_agent_id == "march_7th"
        assert event.interaction_type == "mention_propagation"
        assert event.trigger_reason == "银狼想念三月七"


class TestInterjectionMentionEvent:
    """测试插话提及事件数据结构。"""

    def test_create_event(self) -> None:
        event = InterjectionMentionEvent(
            speaker_agent_id="silver_wolf",
            mentioned_agent_id="march_7th",
            session_id="test_session",
            content_summary="银狼提到了三月七",
        )
        assert event.speaker_agent_id == "silver_wolf"
        assert event.mentioned_agent_id == "march_7th"


class TestInteractionSignalToBehaviorIntent:
    """测试交互信号→行为意图联动。"""

    @pytest.mark.asyncio
    async def test_signal_triggers_intent_production(self) -> None:
        from src.maisaka.agent_autonomy.agent import AutonomousAgent

        agent = AutonomousAgent("march_7th")

        signal = InteractionSignalEvent(
            initiator_agent_id="silver_wolf",
            target_agent_id="march_7th",
            interaction_type="mention_propagation",
            trigger_reason="银狼想念三月七",
        )

        intents = await agent.produce_behavior_intents(
            interaction_signals=[signal],
            intent_threshold=0.0,
        )

        # 交互信号应产生行为意图
        signal_intents = [i for i in intents if i.intent_source == "interaction_signal_driven"]
        assert len(signal_intents) > 0
        assert signal_intents[0].intent_type == "want_to_interject"

    @pytest.mark.asyncio
    async def test_signal_not_for_agent_produces_no_signal_intent(self) -> None:
        from src.maisaka.agent_autonomy.agent import AutonomousAgent

        agent = AutonomousAgent("silver_wolf")

        signal = InteractionSignalEvent(
            initiator_agent_id="march_7th",
            target_agent_id="bronya",
            interaction_type="mention_propagation",
            trigger_reason="三月七想念布洛妮娅",
        )

        intents = await agent.produce_behavior_intents(
            interaction_signals=[signal],
            intent_threshold=0.0,
        )

        signal_intents = [i for i in intents if i.intent_source == "interaction_signal_driven"]
        assert len(signal_intents) == 0


class TestBehaviorIntentPersistence:
    """测试行为意图持久化。"""

    def test_save_and_retrieve(self) -> None:
        from src.maisaka.agent_autonomy.activity_store import AgentActivityStore

        store = AgentActivityStore()
        intent_id = store.save_behavior_intent(
            intent_id="bi:test:abc:123",
            agent_id="silver_wolf",
            session_id="test_session",
            intent_type="want_to_interject",
            intent_strength=75.0,
            intent_source="emotion_driven",
            source_description="情绪excited驱动插话",
        )
        assert intent_id == "bi:test:abc:123"


class TestOrchestratorRegistry:
    """测试编排器注册表。"""

    @pytest.mark.asyncio
    async def test_registry_lookup(self) -> None:
        from src.maisaka.agent_autonomy.orchestrator import AgentOrchestrator
        from unittest.mock import MagicMock

        adapter = MagicMock()
        adapter.current_agent_id = "silver_wolf"

        orchestrator = AgentOrchestrator(
            session_id="test_registry_session",
            session_name="测试会话",
            chat_loop_adapter=adapter,
        )

        found = AgentOrchestrator.get_by_session("test_registry_session")
        assert found is orchestrator

        not_found = AgentOrchestrator.get_by_session("nonexistent")
        assert not_found is None

        # 清理
        AgentOrchestrator._registry.pop("test_registry_session", None)


class TestStructuredLogging:
    """测试结构化日志格式。"""

    @pytest.mark.asyncio
    async def test_activate_log_format(self, caplog: pytest.LogCaptureFixture) -> None:
        import logging

        from src.maisaka.agent_autonomy.orchestrator import AgentOrchestrator
        from unittest.mock import MagicMock

        adapter = MagicMock()
        adapter.current_agent_id = "silver_wolf"

        orchestrator = AgentOrchestrator(
            session_id="test_log_session",
            session_name="日志测试",
            chat_loop_adapter=adapter,
        )

        with caplog.at_level(logging.INFO, logger="agent_autonomy.orchestrator"):
            await orchestrator.activate_agent("silver_wolf", "test")

        log_messages = [r.message for r in caplog.records]
        activate_logs = [m for m in log_messages if "action=activate" in m]
        assert len(activate_logs) > 0
        assert "agent=silver_wolf" in activate_logs[0]

        # 清理
        AgentOrchestrator._registry.pop("test_log_session", None)

    @pytest.mark.asyncio
    async def test_speaker_change_log_format(self, caplog: pytest.LogCaptureFixture) -> None:
        import logging

        from src.maisaka.agent_autonomy.orchestrator import AgentOrchestrator
        from unittest.mock import MagicMock

        adapter = MagicMock()
        adapter.current_agent_id = "silver_wolf"

        orchestrator = AgentOrchestrator(
            session_id="test_sc_log_session",
            session_name="发言权日志测试",
            chat_loop_adapter=adapter,
        )

        with caplog.at_level(logging.INFO, logger="agent_autonomy.orchestrator"):
            await orchestrator.activate_agent("silver_wolf", "test")
            await orchestrator.activate_agent("march_7th", "test")
            await orchestrator.switch_primary_speaker("march_7th", "test_switch")

        log_messages = [r.message for r in caplog.records]
        sc_logs = [m for m in log_messages if "speaker_change" in m]
        assert len(sc_logs) > 0
        assert "from=" in sc_logs[0]
        assert "to=march_7th" in sc_logs[0]

        # 清理
        AgentOrchestrator._registry.pop("test_sc_log_session", None)


class TestInterjectionFeedback:
    """测试插话反哺交互系统。"""

    def test_interjection_mention_event_creation(self) -> None:
        event = InterjectionMentionEvent(
            speaker_agent_id="silver_wolf",
            mentioned_agent_id="bronya",
            session_id="test_session",
            content_summary="银狼提到了布洛妮娅",
        )
        assert event.speaker_agent_id == "silver_wolf"
        assert event.mentioned_agent_id == "bronya"


class TestSignalLoopBreak:
    """测试交互信号与插话的循环打破（冷却机制）。"""

    @pytest.mark.asyncio
    async def test_cooldown_prevents_repeated_interjection(self) -> None:
        from src.maisaka.agent_autonomy.interjection_cooldown import InterjectionCooldownManager

        manager = InterjectionCooldownManager()

        # 第一次应该允许
        assert manager.can_interject("session_1", "silver_wolf") is True

        # 记录插话
        manager.record_interjection("session_1", "silver_wolf")

        # 第二次应该被冷却阻止
        assert manager.can_interject("session_1", "silver_wolf") is False

        # 不同会话不受影响
        assert manager.can_interject("session_2", "silver_wolf") is True

    @pytest.mark.asyncio
    async def test_frequency_limit(self) -> None:
        from src.maisaka.agent_autonomy.interjection_cooldown import InterjectionCooldownManager
        from src.config.config import global_config

        manager = InterjectionCooldownManager()
        max_per_hour = global_config.agent_autonomy.max_interjections_per_hour

        # 模拟达到频率上限
        for i in range(max_per_hour):
            manager.record_interjection("session_1", "silver_wolf")

        # 超过频率上限后应被阻止
        assert manager.can_interject("session_1", "silver_wolf") is False