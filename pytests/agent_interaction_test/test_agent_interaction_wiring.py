"""ZG P1/P2 修复批 6 T6.1：agent_interaction 9 模块生产路径集成测试。

走 bootstrap.py 装配链触发，非自 init（接线四连问④）。
覆盖：bootstrap/engine/scheduler/effect_calculator/emotion_registry/
event_store/relationship_manager/trigger_base/__init__。
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from src.core.app_config_port_registry import (
    reset_app_config_port,
    set_app_config_port,
)
from src.core.types import AgentInteractionSnapshot


# ── 辅助函数 ─────────────────────────────────────────────


def _make_db_session(scalar_result=None, scalars_result=None):
    """构造 get_db_session context manager mock。

    Args:
        scalar_result: session.execute(...).scalar_one_or_none() 返回值
        scalars_result: session.execute(...).scalars().all() 返回值列表
    """
    session = MagicMock()
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=scalar_result)
    scalars_obj = MagicMock()
    scalars_obj.all = MagicMock(return_value=scalars_result or [])
    result.scalars = MagicMock(return_value=scalars_obj)
    session.execute = MagicMock(return_value=result)
    return session


def _make_event_row():
    """构造 InteractionEvent 表行 mock。"""
    row = MagicMock()
    row.event_id = "ie:test:1"
    row.initiator_agent_id = "a1"
    row.target_agent_id = "a2"
    row.interaction_type = "emotion_driven"
    row.trigger_reason = "测试"
    row.content_summary = ""
    row.emotion_effects = "{}"
    row.relationship_effect = 0.0
    row.memory_write_status = "skipped"
    row.echo_depth = 0
    row.echo_parent_event_id = ""
    row.event_metadata = "{}"
    row.created_at = datetime.now()
    return row


def _make_relationship_row(score=100.0, interaction_count=5):
    """构造 AgentInteractionRelationship 表行 mock。"""
    row = MagicMock()
    row.id = 1
    row.agent_id = "a1"
    row.target_agent_id = "a2"
    row.score = score
    row.relationship_type = "friend"
    row.attitude = ""
    row.interaction_count = interaction_count
    row.last_interaction_at = datetime.now()
    row.coactivation_strength = 0.0
    row.last_coactivation_at = 0.0
    row.created_at = datetime.now()
    row.updated_at = datetime.now()
    return row


# ── Fixture ─────────────────────────────────────────────


@pytest.fixture
def agent_config_provider():
    """注册 mock agent_config_provider，返回有效 AgentConfig-like mock。"""
    from src.core.adapters.agent_config_port import (
        reset_agent_config_provider,
        set_agent_config_provider,
    )
    from src.maisaka.agent.emotion import EMOTION_TYPES

    mock_agent_cfg = MagicMock()
    mock_agent_cfg.emotion_baseline = {e: 10 for e in EMOTION_TYPES}
    mock_agent_cfg.event_reaction_rules = []
    mock_agent_cfg.emotion_behavior_map = []
    mock_agent_cfg.display_name = "测试智能体"
    mock_agent_cfg.relationship_growth_rate = 1.0

    provider = MagicMock()
    provider.get_agent.return_value = mock_agent_cfg
    provider.list_agents.return_value = []
    provider.has_agent.return_value = True
    set_agent_config_provider(provider)
    yield provider
    reset_agent_config_provider()


@pytest.fixture
def interaction_config_enabled(agent_config_provider):
    """注册交互配置（enabled=True，monologue 开启）。"""
    cfg = AgentInteractionSnapshot(
        enabled=True,
        monologue_enabled=True,
        evaluation_interval_seconds=10,
    )
    port = MagicMock()
    port.get_agent_interaction_config.return_value = cfg
    set_app_config_port(port)
    yield cfg
    reset_app_config_port()


@pytest.fixture
def interaction_config_disabled(agent_config_provider):
    """交互未启用配置。"""
    cfg = AgentInteractionSnapshot(enabled=False)
    port = MagicMock()
    port.get_agent_interaction_config.return_value = cfg
    set_app_config_port(port)
    yield cfg
    reset_app_config_port()


@pytest.fixture
def interaction_config_monologue_off(agent_config_provider):
    """交互开但独白关。"""
    cfg = AgentInteractionSnapshot(
        enabled=True,
        monologue_enabled=False,
        evaluation_interval_seconds=10,
    )
    port = MagicMock()
    port.get_agent_interaction_config.return_value = cfg
    set_app_config_port(port)
    yield cfg
    reset_app_config_port()


@pytest.fixture
def clean_emotion_singleton():
    """清理 AgentEmotionManagerRegistry 单例类变量（避免跨测试状态污染）。"""
    from src.maisaka.agent_interaction.emotion_registry import (
        AgentEmotionManagerRegistry,
    )

    original = AgentEmotionManagerRegistry._shared_managers
    AgentEmotionManagerRegistry._shared_managers = None
    yield
    AgentEmotionManagerRegistry._shared_managers = original


@pytest.fixture
def bootstrap_scheduler(interaction_config_enabled, clean_emotion_singleton):
    """通过 build_interaction_scheduler 装配链构造 scheduler（生产路径）。"""
    from src.maisaka.agent_interaction.bootstrap import build_interaction_scheduler

    port = MagicMock()
    scheduler = build_interaction_scheduler(port)
    assert scheduler is not None
    return scheduler


# ── bootstrap.py 测试 ───────────────────────────────────


class BootstrapTest:
    """build_interaction_scheduler / build_monologue_engine / get_interaction_engine 装配链测试。"""

    def test_build_scheduler_returns_scheduler_instance(self, bootstrap_scheduler):
        """装配链返回 InteractionScheduler 实例。"""
        from src.maisaka.agent_interaction.scheduler import InteractionScheduler

        assert isinstance(bootstrap_scheduler, InteractionScheduler)

    def test_assembly_chain_complete(self, bootstrap_scheduler):
        """装配链完整闭合：scheduler → trigger → engine → 所有组件已注入（非 None）。"""
        scheduler = bootstrap_scheduler
        # scheduler 持有 trigger
        assert scheduler._trigger is not None
        # trigger 持有 engine/emotion_registry/relationship_manager/cooldown/trigger_registry
        trigger = scheduler._trigger
        assert trigger._engine is not None
        assert trigger._emotion_registry is not None
        assert trigger._relationship_manager is not None
        assert trigger._cooldown_manager is not None
        assert trigger._trigger_registry is not None
        # engine 持有所有组件
        engine = trigger._engine
        assert engine._emotion_registry is not None
        assert engine._relationship_manager is not None
        assert engine._event_store is not None
        assert engine._memory_adapter is not None
        assert engine._effect_calculator is not None
        assert engine._echo_detector is not None
        # trigger_registry 注册了 6 个触发器
        types = trigger._trigger_registry.list_types()
        assert set(types) == {
            "emotion_driven",
            "time_awareness",
            "mention_propagation",
            "event_ripple",
            "inner_need",
            "memory_driven",
        }

    def test_build_scheduler_disabled_returns_none(self, interaction_config_disabled):
        """enabled=False 时返回 None。"""
        from src.maisaka.agent_interaction.bootstrap import (
            build_interaction_scheduler,
        )

        assert build_interaction_scheduler(MagicMock()) is None

    def test_build_scheduler_raises_when_no_config_port(self):
        """get_app_config_port() 返回 None 时抛 RuntimeError。"""
        from src.maisaka.agent_interaction.bootstrap import (
            build_interaction_scheduler,
        )

        reset_app_config_port()
        with pytest.raises(RuntimeError, match="AppConfigPort 未注册"):
            build_interaction_scheduler(MagicMock())

    def test_get_interaction_engine_after_bootstrap(self, bootstrap_scheduler):
        """build_interaction_scheduler 装配后 get_interaction_engine 返回同一 engine 实例。"""
        from src.maisaka.agent_interaction.bootstrap import get_interaction_engine
        from src.maisaka.agent_interaction.engine import InteractionEngine

        engine = get_interaction_engine()
        assert isinstance(engine, InteractionEngine)
        assert engine is bootstrap_scheduler._trigger._engine

    def test_build_monologue_engine_returns_engine(
        self, interaction_config_enabled, clean_emotion_singleton
    ):
        """build_monologue_engine 装配返回 MonologueEngine 实例。"""
        from src.maisaka.agent_interaction.bootstrap import build_monologue_engine
        from src.maisaka.agent_interaction.monologue_engine import MonologueEngine

        engine = build_monologue_engine(MagicMock())
        assert isinstance(engine, MonologueEngine)

    def test_build_monologue_engine_disabled_returns_none(
        self, interaction_config_monologue_off
    ):
        """monologue_enabled=False 时 build_monologue_engine 返回 None。"""
        from src.maisaka.agent_interaction.bootstrap import build_monologue_engine

        assert build_monologue_engine(MagicMock()) is None

    def test_memory_port_injected_through_chain(self, bootstrap_scheduler):
        """memory_port 通过装配链注入到 engine.memory_adapter.memory_port（同一对象）。"""
        from src.maisaka.agent_interaction.bootstrap import (
            build_interaction_scheduler,
        )

        port = MagicMock()
        scheduler = build_interaction_scheduler(port)
        assert scheduler is not None
        memory_adapter = scheduler._trigger._engine._memory_adapter
        assert memory_adapter.memory_port is port


# ── engine.py 测试 ───────────────────────────────────────


class InteractionEngineTest:
    """InteractionEngine 通过 bootstrap 装配后属性验证。"""

    def test_properties_after_bootstrap(
        self, bootstrap_scheduler, interaction_config_enabled
    ):
        """装配后 engine 持有所有组件且配置透传正确。"""
        engine = bootstrap_scheduler._trigger._engine
        assert engine._emotion_registry is not None
        assert engine._relationship_manager is not None
        assert engine._event_store is not None
        assert engine._memory_adapter is not None
        assert engine._echo_max_depth == interaction_config_enabled.echo_max_depth
        assert engine._echo_decay_ratio == interaction_config_enabled.echo_decay_ratio

    def test_echo_detector_assembled(self, bootstrap_scheduler):
        """装配后 EchoDetector 已注入（共享主引擎组件）。"""
        engine = bootstrap_scheduler._trigger._engine
        assert engine._echo_detector is not None

    def test_effect_calculator_assembled(self, bootstrap_scheduler):
        """装配后 EffectCalculator 已构造。"""
        from src.maisaka.agent_interaction.effect_calculator import EffectCalculator

        engine = bootstrap_scheduler._trigger._engine
        assert isinstance(engine._effect_calculator, EffectCalculator)

    def test_interaction_result_defaults(self):
        """InteractionResult 默认值正确。"""
        from src.maisaka.agent_interaction.engine import InteractionResult

        result = InteractionResult()
        assert result.success is False
        assert result.event_id == ""
        assert result.emotion_effects == {}
        assert result.relationship_effect == 0.0
        assert result.memory_write_status == "skipped"
        assert result.echo_triggered is False
        assert result.error == ""


# ── scheduler.py 测试 ────────────────────────────────────


class InteractionSchedulerTest:
    """InteractionScheduler 通过 bootstrap 装配后属性验证。"""

    def test_interval_from_config(
        self, bootstrap_scheduler, interaction_config_enabled
    ):
        """调度间隔从配置透传。"""
        assert (
            bootstrap_scheduler._interval
            == interaction_config_enabled.evaluation_interval_seconds
        )

    def test_holds_trigger(self, bootstrap_scheduler):
        """scheduler 持有 InteractionTrigger 实例。"""
        from src.maisaka.agent_interaction.trigger_scheduler import (
            InteractionTrigger,
        )

        assert isinstance(bootstrap_scheduler._trigger, InteractionTrigger)

    def test_holds_monologue_engine(self, bootstrap_scheduler):
        """scheduler 持有 MonologueEngine 实例（monologue 开启时）。"""
        from src.maisaka.agent_interaction.monologue_engine import MonologueEngine

        assert isinstance(
            bootstrap_scheduler._monologue_engine, MonologueEngine
        )

    def test_initial_state_not_running(self, bootstrap_scheduler):
        """构造后未启动：_running=False, _task=None。"""
        assert bootstrap_scheduler._running is False
        assert bootstrap_scheduler._task is None

    def test_monologue_off_scheduler_has_no_engine(
        self, interaction_config_monologue_off, clean_emotion_singleton
    ):
        """独白关闭时 scheduler._monologue_engine is None（不报错）。"""
        from src.maisaka.agent_interaction.bootstrap import (
            build_interaction_scheduler,
        )

        scheduler = build_interaction_scheduler(MagicMock())
        assert scheduler is not None
        assert scheduler._monologue_engine is None


# ── effect_calculator.py 测试 ────────────────────────────


class EffectCalculatorTest:
    """EffectCalculator 计算逻辑测试（纯函数，无外部依赖）。"""

    def test_calculate_emotion_driven_friend(self):
        """emotion_driven × friend 规则正确。"""
        from src.maisaka.agent_interaction.effect_calculator import (
            EffectCalculator,
        )

        calc = EffectCalculator()
        effect = calc.calculate(
            interaction_type="emotion_driven",
            relationship_type="friend",
            initiator_emotion="lonely",
            target_emotion="calm",
        )
        assert not effect.is_empty
        assert effect.initiator_emotion_deltas["lonely"] == -8
        assert effect.initiator_emotion_deltas["happy"] == 5
        assert effect.target_emotion_deltas["happy"] == 3
        assert effect.relationship_delta == 2.0
        assert effect.emotion_tag == "positive"

    def test_echo_decay_reduces_effect(self):
        """回声深度 > 0 时影响量按 echo_decay_ratio^depth 衰减。"""
        from src.maisaka.agent_interaction.effect_calculator import (
            EffectCalculator,
        )

        calc = EffectCalculator(echo_decay_ratio=0.5)
        direct = calc.calculate(
            "emotion_driven", "friend", "lonely", "calm", echo_depth=0
        )
        echo1 = calc.calculate(
            "emotion_driven", "friend", "lonely", "calm", echo_depth=1
        )
        assert (
            abs(echo1.initiator_emotion_deltas["lonely"])
            == abs(direct.initiator_emotion_deltas["lonely"]) * 0.5
        )
        assert echo1.relationship_delta == direct.relationship_delta * 0.5

    def test_echo_depth_2_double_decay(self):
        """回声深度 2 时衰减为 0.25 倍。"""
        from src.maisaka.agent_interaction.effect_calculator import (
            EffectCalculator,
        )

        calc = EffectCalculator(echo_decay_ratio=0.5)
        direct = calc.calculate(
            "emotion_driven", "friend", "lonely", "calm", echo_depth=0
        )
        echo2 = calc.calculate(
            "emotion_driven", "friend", "lonely", "calm", echo_depth=2
        )
        assert (
            abs(echo2.initiator_emotion_deltas["lonely"])
            == abs(direct.initiator_emotion_deltas["lonely"]) * 0.25
        )

    def test_unknown_interaction_type_uses_default_rule(self):
        """未知交互类型回退到默认规则。"""
        from src.maisaka.agent_interaction.effect_calculator import (
            EffectCalculator,
        )

        calc = EffectCalculator()
        effect = calc.calculate(
            "nonexistent_type", "friend", "calm", "calm"
        )
        assert not effect.is_empty
        assert "happy" in effect.initiator_emotion_deltas

    def test_unknown_relationship_type_uses_default_rule(self):
        """未知关系类型回退到默认规则。"""
        from src.maisaka.agent_interaction.effect_calculator import (
            EffectCalculator,
        )

        calc = EffectCalculator()
        effect = calc.calculate(
            "emotion_driven", "unknown_rel", "lonely", "calm"
        )
        assert not effect.is_empty
        assert "happy" in effect.initiator_emotion_deltas

    def test_emerged_type_resolved_to_known(self):
        """emerged_friend 映射到 friend 规则。"""
        from src.maisaka.agent_interaction.effect_calculator import (
            EffectCalculator,
        )

        calc = EffectCalculator()
        effect = calc.calculate(
            "emotion_driven", "emerged_friend", "lonely", "calm"
        )
        assert not effect.is_empty
        # friend 规则: lonely=-8, happy=5
        assert effect.initiator_emotion_deltas["lonely"] == -8

    def test_emerged_unknown_type_resolved_to_friend(self):
        """emerged_unknown 映射到 friend（兜底）。"""
        from src.maisaka.agent_interaction.effect_calculator import (
            EffectCalculator,
        )

        calc = EffectCalculator()
        effect = calc.calculate(
            "emotion_driven", "emerged_unknown", "lonely", "calm"
        )
        assert not effect.is_empty
        assert effect.initiator_emotion_deltas["lonely"] == -8

    def test_interaction_effect_is_empty_default(self):
        """InteractionEffect 默认值为空。"""
        from src.maisaka.agent_interaction.effect_calculator import (
            InteractionEffect,
        )

        effect = InteractionEffect()
        assert effect.is_empty

    def test_interaction_effect_not_empty_with_relationship_delta(self):
        """有 relationship_delta 时非空。"""
        from src.maisaka.agent_interaction.effect_calculator import (
            InteractionEffect,
        )

        effect = InteractionEffect(relationship_delta=1.0)
        assert not effect.is_empty

    def test_interaction_effect_not_empty_with_emotion_delta(self):
        """有 emotion_delta 时非空。"""
        from src.maisaka.agent_interaction.effect_calculator import (
            InteractionEffect,
        )

        effect = InteractionEffect(initiator_emotion_deltas={"happy": 5.0})
        assert not effect.is_empty


# ── emotion_registry.py 测试 ─────────────────────────────


class AgentEmotionManagerRegistryTest:
    """AgentEmotionManagerRegistry 单例行为和 get_emotion_manager 测试。"""

    def test_singleton_shared_managers(self, bootstrap_scheduler):
        """两个 registry 实例共享同一 _managers 字典（单例语义）。"""
        from src.maisaka.agent_interaction.emotion_registry import (
            AgentEmotionManagerRegistry,
        )

        registry1 = bootstrap_scheduler._trigger._engine._emotion_registry
        registry2 = AgentEmotionManagerRegistry()
        assert registry1._managers is registry2._managers

    def test_get_emotion_manager_returns_emotion_manager(
        self, bootstrap_scheduler, agent_config_provider
    ):
        """get_emotion_manager 返回 EmotionManager 实例。"""
        from src.maisaka.agent.emotion import EmotionManager

        registry = bootstrap_scheduler._trigger._engine._emotion_registry
        manager = registry.get_emotion_manager("ut:emotion:test_agent_1")
        assert isinstance(manager, EmotionManager)

    def test_get_emotion_manager_caches_instance(
        self, bootstrap_scheduler, agent_config_provider
    ):
        """同一 agent_id 多次调用返回同一 EmotionManager 实例（缓存）。"""
        registry = bootstrap_scheduler._trigger._engine._emotion_registry
        m1 = registry.get_emotion_manager("ut:emotion:cache_agent")
        m2 = registry.get_emotion_manager("ut:emotion:cache_agent")
        assert m1 is m2

    def test_get_emotion_state_returns_state(
        self, bootstrap_scheduler, agent_config_provider
    ):
        """get_emotion_state 返回 EmotionState 实例。"""
        from src.maisaka.agent.emotion import EmotionState

        registry = bootstrap_scheduler._trigger._engine._emotion_registry
        state = registry.get_emotion_state("ut:emotion:state_agent")
        assert isinstance(state, EmotionState)

    def test_apply_trigger_modifies_emotion(
        self, bootstrap_scheduler, agent_config_provider
    ):
        """apply_trigger 增加情绪强度。"""
        registry = bootstrap_scheduler._trigger._engine._emotion_registry
        agent_id = "ut:emotion:apply_agent"
        state_before = registry.get_emotion_state(agent_id)
        happy_before = state_before.emotions["happy"]
        registry.apply_trigger(agent_id, "happy", 20.0)
        state_after = registry.get_emotion_state(agent_id)
        assert state_after.emotions["happy"] == happy_before + 20.0


# ── event_store.py 测试 ──────────────────────────────────


class InteractionEventStoreTest:
    """InteractionEventStore 基本操作测试（mock db session）。"""

    async def test_save_event_returns_event_id(self, bootstrap_scheduler):
        """save_event 返回 event_id 且 session.add/commit 被调用。"""
        from src.maisaka.agent_interaction.models import InteractionEventCreate

        store = bootstrap_scheduler._trigger._engine._event_store
        event_data = InteractionEventCreate(
            initiator_agent_id="a1",
            target_agent_id="a2",
            interaction_type="emotion_driven",
            trigger_reason="测试保存",
        )
        session = _make_db_session()
        with patch(
            "src.maisaka.agent_interaction.event_store.get_db_session",
            return_value=session,
        ):
            event_id = await store.save_event(event_data)
        assert event_id.startswith("ie:a1:")
        session.add.assert_called_once()
        session.commit.assert_called_once()

    async def test_get_event_found(self, bootstrap_scheduler):
        """get_event 找到事件时返回 InteractionEventRead。"""
        store = bootstrap_scheduler._trigger._engine._event_store
        mock_row = _make_event_row()
        session = _make_db_session(scalar_result=mock_row)
        with patch(
            "src.maisaka.agent_interaction.event_store.get_db_session",
            return_value=session,
        ):
            event = await store.get_event("ie:test:1")
        assert event is not None
        assert event.event_id == "ie:test:1"
        assert event.initiator_agent_id == "a1"
        assert event.target_agent_id == "a2"

    async def test_get_event_not_found(self, bootstrap_scheduler):
        """get_event 未找到时返回 None。"""
        store = bootstrap_scheduler._trigger._engine._event_store
        session = _make_db_session(scalar_result=None)
        with patch(
            "src.maisaka.agent_interaction.event_store.get_db_session",
            return_value=session,
        ):
            event = await store.get_event("ie:nonexistent")
        assert event is None

    async def test_query_events_returns_list(self, bootstrap_scheduler):
        """query_events 返回事件列表。"""
        store = bootstrap_scheduler._trigger._engine._event_store
        mock_row = _make_event_row()
        session = _make_db_session(scalars_result=[mock_row])
        with patch(
            "src.maisaka.agent_interaction.event_store.get_db_session",
            return_value=session,
        ):
            events = await store.query_events(agent_id="a1")
        assert len(events) == 1
        assert events[0].initiator_agent_id == "a1"

    async def test_get_recent_events_returns_list(self, bootstrap_scheduler):
        """get_recent_events 返回最近事件列表。"""
        store = bootstrap_scheduler._trigger._engine._event_store
        mock_row = _make_event_row()
        session = _make_db_session(scalars_result=[mock_row])
        with patch(
            "src.maisaka.agent_interaction.event_store.get_db_session",
            return_value=session,
        ):
            events = await store.get_recent_events(limit=5)
        assert len(events) == 1


# ── relationship_manager.py 测试 ─────────────────────────


class AgentRelationshipManagerTest:
    """AgentRelationshipManager 基本操作测试（mock db session）。"""

    def test_resolve_effect_type_known(self):
        """emerged_ 已知类型映射正确。"""
        from src.maisaka.agent_interaction.relationship_manager import (
            AgentRelationshipManager,
        )

        assert AgentRelationshipManager.resolve_effect_type("emerged_friend") == "friend"
        assert AgentRelationshipManager.resolve_effect_type("emerged_family") == "family"
        assert (
            AgentRelationshipManager.resolve_effect_type("emerged_romantic")
            == "romantic"
        )
        assert AgentRelationshipManager.resolve_effect_type("emerged_mentor") == "mentor"
        assert AgentRelationshipManager.resolve_effect_type("emerged_rival") == "rival"

    def test_resolve_effect_type_unknown_to_friend(self):
        """emerged_ 未知类型兜底到 friend。"""
        from src.maisaka.agent_interaction.relationship_manager import (
            AgentRelationshipManager,
        )

        assert AgentRelationshipManager.resolve_effect_type("emerged_unknown") == "friend"
        assert (
            AgentRelationshipManager.resolve_effect_type("emerged_group") == "friend"
        )

    def test_resolve_effect_type_non_emerged_passthrough(self):
        """非 emerged_ 类型原样返回。"""
        from src.maisaka.agent_interaction.relationship_manager import (
            AgentRelationshipManager,
        )

        assert AgentRelationshipManager.resolve_effect_type("friend") == "friend"
        assert AgentRelationshipManager.resolve_effect_type("rival") == "rival"
        assert AgentRelationshipManager.resolve_effect_type("family") == "family"

    async def test_get_relationship_found(self, bootstrap_scheduler):
        """get_relationship 找到关系时返回 AgentInteractionRelationshipRead。"""
        mgr = bootstrap_scheduler._trigger._engine._relationship_manager
        mock_row = _make_relationship_row()
        session = _make_db_session(scalar_result=mock_row)
        with patch(
            "src.maisaka.agent_interaction.relationship_manager.get_db_session",
            return_value=session,
        ):
            rel = await mgr.get_relationship("a1", "a2")
        assert rel is not None
        assert rel.agent_id == "a1"
        assert rel.target_agent_id == "a2"
        assert rel.relationship_type == "friend"

    async def test_get_relationship_not_found(self, bootstrap_scheduler):
        """get_relationship 未找到时返回 None。"""
        mgr = bootstrap_scheduler._trigger._engine._relationship_manager
        session = _make_db_session(scalar_result=None)
        with patch(
            "src.maisaka.agent_interaction.relationship_manager.get_db_session",
            return_value=session,
        ):
            rel = await mgr.get_relationship("a1", "nonexistent")
        assert rel is None

    async def test_update_relationship_existing(self, bootstrap_scheduler):
        """update_relationship 更新已存在关系的分数。"""
        mgr = bootstrap_scheduler._trigger._engine._relationship_manager
        mock_row = _make_relationship_row(score=100.0, interaction_count=5)
        session = _make_db_session(scalar_result=mock_row)
        with patch(
            "src.maisaka.agent_interaction.relationship_manager.get_db_session",
            return_value=session,
        ):
            result = await mgr.update_relationship("a1", "a2", 50.0)
        assert result.score == 150.0
        session.commit.assert_called_once()
        session.refresh.assert_called_once()


# ── trigger_base.py 测试 ─────────────────────────────────


class TriggerRegistryTest:
    """TriggerRegistry register/get/list_types/all_triggers 测试。"""

    def test_register_and_get(self):
        """register 后 get 返回同一触发器实例。"""
        from src.maisaka.agent_interaction.trigger_base import (
            BaseTrigger,
            TriggerRegistry,
        )

        registry = TriggerRegistry()
        trigger = MagicMock(spec=BaseTrigger)
        registry.register("test_type", trigger)
        assert registry.get("test_type") is trigger

    def test_get_unknown_returns_none(self):
        """get 未注册类型返回 None。"""
        from src.maisaka.agent_interaction.trigger_base import TriggerRegistry

        registry = TriggerRegistry()
        assert registry.get("unknown") is None

    def test_register_overwrite(self):
        """register 同名类型覆盖旧触发器。"""
        from src.maisaka.agent_interaction.trigger_base import (
            BaseTrigger,
            TriggerRegistry,
        )

        registry = TriggerRegistry()
        t1 = MagicMock(spec=BaseTrigger)
        t2 = MagicMock(spec=BaseTrigger)
        registry.register("type_a", t1)
        registry.register("type_a", t2)
        assert registry.get("type_a") is t2

    def test_list_types(self):
        """list_types 返回所有已注册类型。"""
        from src.maisaka.agent_interaction.trigger_base import (
            BaseTrigger,
            TriggerRegistry,
        )

        registry = TriggerRegistry()
        registry.register("a", MagicMock(spec=BaseTrigger))
        registry.register("b", MagicMock(spec=BaseTrigger))
        assert set(registry.list_types()) == {"a", "b"}

    def test_all_triggers(self):
        """all_triggers 返回 (type, trigger) 元组列表。"""
        from src.maisaka.agent_interaction.trigger_base import (
            BaseTrigger,
            TriggerRegistry,
        )

        registry = TriggerRegistry()
        t1 = MagicMock(spec=BaseTrigger)
        registry.register("a", t1)
        triggers = registry.all_triggers()
        assert len(triggers) == 1
        assert triggers[0][0] == "a"
        assert triggers[0][1] is t1

    def test_empty_registry_list_types(self):
        """空注册表 list_types 返回空列表。"""
        from src.maisaka.agent_interaction.trigger_base import TriggerRegistry

        registry = TriggerRegistry()
        assert registry.list_types() == []
        assert registry.all_triggers() == []


class BaseTriggerTest:
    """BaseTrigger 抽象基类与 TriggerEvaluation dataclass 测试。"""

    def test_trigger_evaluation_defaults(self):
        """TriggerEvaluation 默认值正确。"""
        from src.maisaka.agent_interaction.trigger_base import TriggerEvaluation

        ev = TriggerEvaluation()
        assert ev.should_trigger is False
        assert ev.trigger_probability == 0.0
        assert ev.initiator_agent_id == ""
        assert ev.target_agent_id == ""
        assert ev.interaction_type == ""
        assert ev.trigger_reason == ""
        assert ev.metadata == {}

    def test_trigger_evaluation_custom_values(self):
        """TriggerEvaluation 自定义值正确。"""
        from src.maisaka.agent_interaction.trigger_base import TriggerEvaluation

        ev = TriggerEvaluation(
            should_trigger=True,
            trigger_probability=0.8,
            initiator_agent_id="a1",
            target_agent_id="a2",
            interaction_type="emotion_driven",
            trigger_reason="测试",
            metadata={"echo_depth": 2},
        )
        assert ev.should_trigger is True
        assert ev.trigger_probability == 0.8
        assert ev.initiator_agent_id == "a1"
        assert ev.metadata["echo_depth"] == 2

    async def test_concrete_subclass_evaluate(self):
        """BaseTrigger 具体子类 evaluate 方法可调用并返回 TriggerEvaluation。"""
        from src.maisaka.agent.emotion import EmotionState
        from src.maisaka.agent_interaction.trigger_base import (
            BaseTrigger,
            TriggerEvaluation,
        )

        class _ConcreteTrigger(BaseTrigger):
            async def evaluate(
                self,
                agent_id,
                emotion_state,
                relationships,
                memory_context=None,
                time_context=None,
            ):
                return TriggerEvaluation(
                    should_trigger=True,
                    initiator_agent_id=agent_id,
                )

        trigger = _ConcreteTrigger()
        state = EmotionState()
        result = await trigger.evaluate("a1", state, [])
        assert result.should_trigger is True
        assert result.initiator_agent_id == "a1"


# ── __init__.py 导出测试 ─────────────────────────────────


class ModuleExportsTest:
    """agent_interaction 包导出完整性测试。"""

    def test_all_exports_present(self):
        """__init__.py 导出所有核心类。"""
        import src.maisaka.agent_interaction as mod

        expected = {
            "AgentInteractionRelationshipCreate",
            "AgentInteractionRelationshipRead",
            "BaseTrigger",
            "EffectCalculator",
            "EmotionDrivenTrigger",
            "EventRippleTrigger",
            "InnerNeedTrigger",
            "InnerMonologueEventRead",
            "InteractionCooldownRead",
            "InteractionEffect",
            "InteractionEngine",
            "InteractionEventCreate",
            "InteractionEventRead",
            "InteractionResult",
            "InteractionScheduler",
            "MentionPropagationTrigger",
            "TimeAwarenessTrigger",
            "TriggerEvaluation",
            "TriggerRegistry",
        }
        for name in expected:
            assert hasattr(mod, name), f"__init__.py 缺少导出: {name}"

    def test_exports_match_all(self):
        """__all__ 列表与实际导出一致。"""
        import src.maisaka.agent_interaction as mod

        assert mod.__all__ is not None
        for name in mod.__all__:
            assert hasattr(mod, name), f"__all__ 声明但未导出: {name}"

    def test_exported_classes_are_types(self):
        """导出的核心类是 type（类对象）。"""
        import src.maisaka.agent_interaction as mod

        for cls_name in (
            "InteractionEngine",
            "InteractionScheduler",
            "EffectCalculator",
            "TriggerRegistry",
            "BaseTrigger",
        ):
            obj = getattr(mod, cls_name)
            assert isinstance(obj, type), f"{cls_name} 不是类对象"