"""agent_context_identity 两开关的三处同步测试（批次 1）。"""

import tomllib

from dataclasses import fields
from types import SimpleNamespace

from src.config.official_configs import AgentAutonomySectionConfig
from src.core.adapters.app_config_port import GlobalConfigAppConfigPort
from src.core.types import AgentAutonomySnapshot


FLAGS = ("context_identity_enabled", "self_narration_first_person")


def test_snapshot_defaults_false():
    snapshot = AgentAutonomySnapshot()

    assert snapshot.context_identity_enabled is False
    assert snapshot.self_narration_first_person is False


def test_section_fields_exist_with_false_default():
    for name in FLAGS:
        field = AgentAutonomySectionConfig.model_fields[name]
        assert field.default is False
        extra = field.json_schema_extra
        assert extra["advanced"] is True
        assert extra["x-widget"] == "switch"
        label = extra["label"]
        assert label["zh_CN"]
        assert label["en_US"]
        assert label["ja_JP"]


def test_three_sites_have_same_flags():
    section_fields = set(AgentAutonomySectionConfig.model_fields)
    snapshot_fields = {field.name for field in fields(AgentAutonomySnapshot)}

    for name in FLAGS:
        assert name in section_fields
        assert name in snapshot_fields


def test_port_reads_true_from_section(monkeypatch):
    section = AgentAutonomySectionConfig(
        context_identity_enabled=True,
        self_narration_first_person=True,
    )
    port = GlobalConfigAppConfigPort()
    monkeypatch.setattr(port, "_get_cfg", lambda: SimpleNamespace(agent_autonomy=section))

    snapshot = port.get_agent_autonomy_config()

    assert snapshot.context_identity_enabled is True
    assert snapshot.self_narration_first_person is True


def test_template_has_flags_false_and_version_bumped():
    with open("config/bot_config.toml", "rb") as file:
        data = tomllib.load(file)

    section = data["agent_autonomy"]
    assert section["context_identity_enabled"] is False
    assert section["self_narration_first_person"] is False
    assert data["inner"]["version"] == "8.29.1"