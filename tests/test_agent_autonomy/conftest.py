"""tests/test_agent_autonomy 共享 fixture — 注册自治架构构造所需的 Port。"""

from types import SimpleNamespace

import pytest


@pytest.fixture
def agent_autonomy_ports():
    """注册 AgentOrchestrator/InterjectionCooldownManager 依赖的核心 Port。"""
    from unittest.mock import MagicMock

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
    autonomy_config = SimpleNamespace(
        orchestrator_strategy="default",
        vitality_tick_interval_seconds=3600,
        max_active_agents=4,
        state_awareness_enabled=False,
        interjection_cooldown_minutes=1,
        max_interjections_per_hour=5,
        max_interjections_per_session_per_hour=10,
        # ZG-23a: 出站去重 + 发言节流配置
        outbound_dedup_window_seconds=3.0,
        outbound_dedup_max_entries=5000,
        mention_chain_decay_base=0.6,
        mention_chain_max_depth=4,
        cohabitation_decay_factor=0.5,
        cohabitation_min_max=2,
        # ZH-1: 角色参数漂移配置
        zh1_role_drift_enabled=False,
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
    app_config_port.get_agent_autonomy_config.return_value = autonomy_config
    event_bus_port = MagicMock()

    set_app_config_port(app_config_port)
    set_event_bus_port(event_bus_port)
    register_routing_service(MagicMock())

    yield SimpleNamespace(
        app_config=app_config_port,
        autonomy_config=autonomy_config,
        event_bus=event_bus_port,
    )

    reset_app_config_port()
    reset_event_bus_port()
    register_routing_service(None)
