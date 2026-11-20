"""管家收尾配置三处同步 —— 经真实 Port 读路径验证。

三处 = AgentAutonomySectionConfig（schema）→ AgentAutonomySnapshot（快照）
→ GlobalConfigAppConfigPort.get_agent_autonomy_config（白名单拷贝）。
断言一律用非默认值，防止「断言撞默认值」假绿。
"""

from types import SimpleNamespace

import pytest

from src.config.official_configs import AgentAutonomySectionConfig
from src.core.adapters.app_config_port import GlobalConfigAppConfigPort
from src.core.types import AgentAutonomySnapshot
from src.maisaka.agent_autonomy.butler_closure import ButlerClosureConfig


NON_DEFAULTS = {
    "butler_scene_opening_enabled": False,
    "butler_opening_silence_minutes": 45,
    "butler_topic_budget": 3,
    "butler_opening_max_chars": 200,
    "butler_opening_timeout_seconds": 9.5,
    "butler_closure_round_enabled": False,
}


def _port_with_section(section: AgentAutonomySectionConfig, monkeypatch) -> GlobalConfigAppConfigPort:
    port = GlobalConfigAppConfigPort()
    monkeypatch.setattr(port, "_get_cfg", lambda: SimpleNamespace(agent_autonomy=section))
    return port


def test_port_reads_non_default_values(monkeypatch):
    section = AgentAutonomySectionConfig(**NON_DEFAULTS)
    snapshot = _port_with_section(section, monkeypatch).get_agent_autonomy_config()

    assert snapshot.butler_scene_opening_enabled is False
    assert snapshot.butler_opening_silence_minutes == 45
    assert snapshot.butler_topic_budget == 3
    assert snapshot.butler_opening_max_chars == 200
    assert snapshot.butler_opening_timeout_seconds == 9.5
    assert snapshot.butler_closure_round_enabled is False


def test_asserted_values_differ_from_defaults():
    section = AgentAutonomySectionConfig()
    snapshot = AgentAutonomySnapshot()

    for name, value in NON_DEFAULTS.items():
        assert getattr(section, name) != value, f"{name} 的断言值撞上了配置类默认值"
        assert getattr(snapshot, name) != value, f"{name} 的断言值撞上了快照默认值"


def test_defaults_match_butler_closure_config():
    config = ButlerClosureConfig()
    section = AgentAutonomySectionConfig()
    snapshot = AgentAutonomySnapshot()

    pairs = (
        ("opening_enabled", "butler_scene_opening_enabled"),
        ("silence_threshold_minutes", "butler_opening_silence_minutes"),
        ("budget_limit", "butler_topic_budget"),
        ("opening_max_chars", "butler_opening_max_chars"),
        ("opening_timeout_seconds", "butler_opening_timeout_seconds"),
        ("closure_enabled", "butler_closure_round_enabled"),
    )
    for config_field, field_name in pairs:
        expected = getattr(config, config_field)
        assert getattr(section, field_name) == expected
        assert getattr(snapshot, field_name) == expected


def test_schema_extra_complete_for_all_six_fields():
    for name in NON_DEFAULTS:
        extra = AgentAutonomySectionConfig.model_fields[name].json_schema_extra
        assert extra is not None, f"{name} 缺 json_schema_extra"
        label = extra["label"]
        assert label["zh_CN"]
        assert label["en_US"]
        assert label["ja_JP"]
        assert extra["x-widget"]
        assert extra["x-icon"]


def test_field_constraints():
    fields = AgentAutonomySectionConfig.model_fields

    assert fields["butler_opening_silence_minutes"].metadata
    assert fields["butler_topic_budget"].metadata
    assert fields["butler_opening_max_chars"].metadata
    assert fields["butler_opening_timeout_seconds"].metadata

    with pytest.raises(ValueError):
        AgentAutonomySectionConfig(butler_topic_budget=11)
    with pytest.raises(ValueError):
        AgentAutonomySectionConfig(butler_opening_timeout_seconds=0.4)