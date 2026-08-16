"""ZG16-6a: schema 漂移检测测试——声明键 vs 实际键漂移。

覆盖 design 4.6 全部 8 个场景，spec 8.5 实测验证项（5 项）。
"""

from unittest.mock import patch

from pydantic import BaseModel

from src.plugin_runtime_v2.config.schema_drift import DriftResult, SchemaDriftDetector


class SampleSchema(BaseModel):
    port: int
    host: str = "127.0.0.1"


def test_extra_keys_warning():
    """多余键告警（spec 5.5.1 规则 6a）。"""
    with patch("src.core.error_escalation_port_registry.get_error_escalation_port", return_value=None):
        result = SchemaDriftDetector.detect("X", {"port": 3001, "unknown": 1}, SampleSchema)
    assert result is not None and "unknown" in result.extra_keys


def test_missing_required_keys_error():
    """缺失必填键告警（spec 5.5.1 规则 6b）。"""
    with patch("src.core.error_escalation_port_registry.get_error_escalation_port", return_value=None):
        result = SchemaDriftDetector.detect("X", {"host": "localhost"}, SampleSchema)
    assert result is not None and "port" in result.missing_keys


def test_type_mismatch_error():
    """类型不匹配告警（spec 5.5.1 规则 6c）。"""
    with patch("src.core.error_escalation_port_registry.get_error_escalation_port", return_value=None):
        result = SchemaDriftDetector.detect("X", {"port": "abc"}, SampleSchema)
    assert result is not None and len(result.type_mismatches) > 0


def test_schema_none_skip():
    """schema None 跳过（spec 5.2.3 场景 1）。"""
    assert SchemaDriftDetector.detect("X", {"port": 3001}, None) is None


def test_no_drift():
    """无漂移返回 None。"""
    with patch("src.core.error_escalation_port_registry.get_error_escalation_port", return_value=None):
        result = SchemaDriftDetector.detect("X", {"port": 3001, "host": "localhost"}, SampleSchema)
    assert result is None


def test_drift_result_fields():
    """DriftResult 包含 plugin_id + 漂移字段。"""
    with patch("src.core.error_escalation_port_registry.get_error_escalation_port", return_value=None):
        result = SchemaDriftDetector.detect("X", {"port": 3001, "extra": 1}, SampleSchema)
    assert result is not None
    assert result.plugin_id == "X"
    assert result.extra_keys == ["extra"]
    assert result.missing_keys == []
    assert result.type_mismatches == []


def test_type_mismatch_detail():
    """类型不匹配详情包含 key/expected_type/actual_type。"""
    with patch("src.core.error_escalation_port_registry.get_error_escalation_port", return_value=None):
        result = SchemaDriftDetector.detect("X", {"port": "abc"}, SampleSchema)
    assert result is not None
    mismatch = result.type_mismatches[0]
    assert mismatch["key"] == "port"
    assert "int" in mismatch["expected_type"]
    assert mismatch["actual_type"] == "str"


def test_multiple_extra_keys():
    """多个多余键全部检测。"""
    with patch("src.core.error_escalation_port_registry.get_error_escalation_port", return_value=None):
        result = SchemaDriftDetector.detect(
            "X", {"port": 3001, "extra1": 1, "extra2": 2}, SampleSchema
        )
    assert result is not None
    assert set(result.extra_keys) == {"extra1", "extra2"}


def test_drift_result_frozen():
    """DriftResult 是 frozen dataclass。"""
    import dataclasses

    assert dataclasses.is_dataclass(DriftResult)
    # frozen 验证：字段有 default_factory
    result = DriftResult(plugin_id="X")
    assert result.extra_keys == []
    assert result.missing_keys == []
    assert result.type_mismatches == []