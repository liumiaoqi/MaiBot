"""P0-3: ZH-1 漂移系统接线测试——验证创建→注册→触发生产路径。

四连问④：测试走生产路径，不许自己 init 自己。
验证 orchestrator.__init__ → _build_drift_tick_callback → VitalityTickScheduler 注册 → 回调可触发。
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


def _make_autonomy_config(enabled: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        orchestrator_strategy="default",
        vitality_tick_interval_seconds=3600,
        max_active_agents=4,
        state_awareness_enabled=False,
        interjection_cooldown_minutes=1,
        max_interjections_per_hour=5,
        max_interjections_per_session_per_hour=10,
        outbound_dedup_window_seconds=3.0,
        outbound_dedup_max_entries=5000,
        mention_chain_decay_base=0.6,
        mention_chain_max_depth=4,
        cohabitation_decay_factor=0.5,
        cohabitation_min_max=2,
        zh1_role_drift_enabled=enabled,
        zh1_role_drift_drift_period=500,
        zh1_role_drift_regression_rate=0.03,
        zh1_role_drift_sigma_max=0.3,
        zh1_role_drift_selection_ratio=0.167,
        zh1_role_drift_w_interaction=0.4,
        zh1_role_drift_w_relation=0.2,
        zh1_role_drift_w_uniqueness=0.3,
        zh1_role_drift_w_emotion=0.0,
        zh1_role_drift_reflection_interval=3600,
    )


@pytest.fixture
def drift_enabled_ports():
    """注册 zh1_role_drift_enabled=True 的 Port。"""
    from src.core.app_config_port_registry import (
        reset_app_config_port,
        set_app_config_port,
    )
    from src.core.event_bus_port_registry import (
        reset_event_bus_port,
        set_event_bus_port,
    )
    from src.core.routing_port_registry import register_routing_service

    app_config_port = MagicMock()
    app_config_port.get_agent_autonomy_config.return_value = _make_autonomy_config(enabled=True)
    event_bus_port = MagicMock()

    set_app_config_port(app_config_port)
    set_event_bus_port(event_bus_port)
    register_routing_service(MagicMock())

    yield app_config_port

    reset_app_config_port()
    reset_event_bus_port()


@pytest.fixture
def drift_disabled_ports():
    """注册 zh1_role_drift_enabled=False 的 Port。"""
    from src.core.app_config_port_registry import (
        reset_app_config_port,
        set_app_config_port,
    )
    from src.core.event_bus_port_registry import (
        reset_event_bus_port,
        set_event_bus_port,
    )
    from src.core.routing_port_registry import register_routing_service

    app_config_port = MagicMock()
    app_config_port.get_agent_autonomy_config.return_value = _make_autonomy_config(enabled=False)
    event_bus_port = MagicMock()

    set_app_config_port(app_config_port)
    set_event_bus_port(event_bus_port)
    register_routing_service(MagicMock())

    yield app_config_port

    reset_app_config_port()
    reset_event_bus_port()


class TestDriftWiringProductionPath:
    """验证 orchestrator 生产路径正确接线 PersonalityDriftManager。"""

    @pytest.mark.asyncio
    async def test_drift_manager_created_when_enabled(self, drift_enabled_ports):
        """① 生产创建点：enabled=True 时 orchestrator 创建 PersonalityDriftManager。"""
        from src.maisaka.agent_autonomy.orchestrator import AgentOrchestrator
        from src.maisaka.agent_autonomy.personality_drift import PersonalityDriftManager

        orchestrator = AgentOrchestrator(
            session_id="test_drift_wiring",
            session_name="测试",
            chat_loop_adapter=MagicMock(),
            thinking_organ_factory=MagicMock(),
            is_group_chat=False,
        )
        assert orchestrator._drift_manager is not None
        assert isinstance(orchestrator._drift_manager, PersonalityDriftManager)
        orchestrator._vitality_tick_scheduler.stop()
        AgentOrchestrator._registry.pop("test_drift_wiring", None)

    @pytest.mark.asyncio
    async def test_drift_callback_registered_when_enabled(self, drift_enabled_ports):
        """② 注册点：VitalityTickScheduler 收到非 None 的 drift_tick_callback。"""
        from src.maisaka.agent_autonomy.orchestrator import AgentOrchestrator

        orchestrator = AgentOrchestrator(
            session_id="test_drift_cb",
            session_name="测试",
            chat_loop_adapter=MagicMock(),
            thinking_organ_factory=MagicMock(),
            is_group_chat=False,
        )
        assert orchestrator._vitality_tick_scheduler._drift_tick_callback is not None
        orchestrator._vitality_tick_scheduler.stop()
        AgentOrchestrator._registry.pop("test_drift_cb", None)

    @pytest.mark.asyncio
    async def test_drift_manager_none_when_disabled(self, drift_disabled_ports):
        """enabled=False 时不创建 drift_manager。"""
        from src.maisaka.agent_autonomy.orchestrator import AgentOrchestrator

        orchestrator = AgentOrchestrator(
            session_id="test_drift_off",
            session_name="测试",
            chat_loop_adapter=MagicMock(),
            thinking_organ_factory=MagicMock(),
            is_group_chat=False,
        )
        assert orchestrator._drift_manager is None
        orchestrator._vitality_tick_scheduler.stop()
        AgentOrchestrator._registry.pop("test_drift_off", None)

    @pytest.mark.asyncio
    async def test_drift_callback_callable_without_error(self, drift_enabled_ports):
        """③ 触发点：回调可安全调用（无活跃智能体时 no-op，不崩溃）。"""
        from src.maisaka.agent_autonomy.orchestrator import AgentOrchestrator

        orchestrator = AgentOrchestrator(
            session_id="test_drift_trigger",
            session_name="测试",
            chat_loop_adapter=MagicMock(),
            thinking_organ_factory=MagicMock(),
            is_group_chat=False,
        )
        callback = orchestrator._vitality_tick_scheduler._drift_tick_callback
        callback()
        orchestrator._vitality_tick_scheduler.stop()
        AgentOrchestrator._registry.pop("test_drift_trigger", None)
