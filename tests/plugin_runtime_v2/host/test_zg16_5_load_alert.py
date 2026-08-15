"""ZG16-5: check_scopes_completeness + _emit_load_alert 测试。

覆盖 v2 scopes 缺失告警、v1 不触发、Tier 1 缺失 error、
无缺失返回 None、best-effort 不抛。
"""

from unittest.mock import patch

import pytest

from src.plugin_runtime_v2.host.servicer import (
    LoadAlert,
    _emit_load_alert,
    check_scopes_completeness,
)


def _write_code(tmp_path, content):
    """写入 plugin.py 代码文件，返回代码目录字符串。"""
    (tmp_path / "plugin.py").write_text(content, encoding="utf-8")
    return str(tmp_path)


class TestV2ScopesMissing:
    """v2 插件 scopes 缺失 → warning。"""

    def test_v2_scopes_missing(self, tmp_path):
        """v2 插件无 scopes 字段 → LoadAlert(warning)。"""
        manifest = {"id": "org.test", "version": "1.0"}
        alert = check_scopes_completeness(
            plugin_id="org.test", manifest=manifest, is_v2=True,
        )
        assert alert is not None
        assert alert.alert_level == "warning"
        assert alert.is_tier1 is False

    def test_v2_scopes_empty(self, tmp_path):
        """v2 插件 scopes=[] → LoadAlert(warning)。"""
        manifest = {"scopes": []}
        alert = check_scopes_completeness(
            plugin_id="org.test", manifest=manifest, is_v2=True,
        )
        assert alert is not None
        assert alert.alert_level == "warning"


class TestV1NotTriggered:
    """v1 插件不触发。"""

    def test_v1_not_triggered(self, tmp_path):
        manifest = {"scopes": []}
        alert = check_scopes_completeness(
            plugin_id="org.test", manifest=manifest, is_v2=False,
        )
        assert alert is None

    def test_v1_no_scopes_not_triggered(self, tmp_path):
        manifest = {"id": "org.test"}
        alert = check_scopes_completeness(
            plugin_id="org.test", manifest=manifest, is_v2=False,
        )
        assert alert is None


class TestTier1MissingError:
    """Tier 1 缺失 → error。"""

    def test_tier1_missing_error(self, tmp_path):
        """代码含 CLI 但 manifest 无 system:execute:cli → error。"""
        code_dir = _write_code(tmp_path, "import subprocess\nsubprocess.run(['ls'])\n")
        manifest = {"scopes": ["message:send:text"]}
        alert = check_scopes_completeness(
            plugin_id="org.test",
            manifest=manifest,
            is_v2=True,
            plugin_code_path=code_dir,
        )
        assert alert is not None
        assert alert.alert_level == "error"
        assert alert.is_tier1 is True
        assert "system:execute:cli" in alert.missing_scopes

    def test_tier1_declaled_no_error(self, tmp_path):
        """代码含 CLI 且 manifest 声明了 → None。"""
        code_dir = _write_code(tmp_path, "import subprocess\nsubprocess.run(['ls'])\n")
        manifest = {"scopes": ["system:execute:cli"]}
        alert = check_scopes_completeness(
            plugin_id="org.test",
            manifest=manifest,
            is_v2=True,
            plugin_code_path=code_dir,
        )
        assert alert is None


class TestNoMissingReturnsNone:
    """无缺失 → None。"""

    def test_no_missing_returns_none(self, tmp_path):
        code_dir = _write_code(tmp_path, "x = 1\n")
        manifest = {"scopes": ["message:send:text"]}
        alert = check_scopes_completeness(
            plugin_id="org.test",
            manifest=manifest,
            is_v2=True,
            plugin_code_path=code_dir,
        )
        assert alert is None

    def test_no_code_path_no_error(self, tmp_path):
        """plugin_code_path=None → 不做 Tier 1 检测 → 有 scopes 时 None。"""
        manifest = {"scopes": ["message:send:text"]}
        alert = check_scopes_completeness(
            plugin_id="org.test",
            manifest=manifest,
            is_v2=True,
            plugin_code_path=None,
        )
        assert alert is None


class TestBestEffortFailure:
    """告警逻辑崩溃 → 不抛异常。"""

    def test_emit_load_alert_crash_does_not_raise(self):
        """_emit_load_alert 内部异常不外抛。"""
        alert = LoadAlert(
            plugin_id="org.test",
            alert_level="error",
            missing_scopes=["system:execute:cli"],
            is_tier1=True,
            timestamp=0.0,
        )
        # mock error_escalation port 导入失败
        with patch("src.core.error_escalation_port_registry.get_error_escalation_port",
                    side_effect=ImportError("boom")):
            # 不应抛异常
            _emit_load_alert(alert)

    def test_check_scopes_detector_crash_returns_none(self, tmp_path):
        """Tier1Detector 异常 → 降级返回 None。"""
        manifest = {"scopes": ["message:send:text"]}
        with patch(
            "src.plugin_runtime_v2.host.servicer.Tier1Detector.detect",
            side_effect=RuntimeError("detect boom"),
        ):
            alert = check_scopes_completeness(
                plugin_id="org.test",
                manifest=manifest,
                is_v2=True,
                plugin_code_path=str(tmp_path),
            )
            assert alert is None


class TestLoadAlertDataclass:
    """LoadAlert 数据类。"""

    def test_load_alert_fields(self):
        alert = LoadAlert(
            plugin_id="X",
            alert_level="warning",
            missing_scopes=[],
            is_tier1=False,
            timestamp=1.0,
        )
        assert alert.plugin_id == "X"
        assert alert.alert_level == "warning"
        assert alert.missing_scopes == []
        assert alert.is_tier1 is False
        assert alert.timestamp == 1.0

    def test_load_alert_frozen(self):
        alert = LoadAlert(
            plugin_id="X", alert_level="warning", is_tier1=False, timestamp=0.0,
        )
        with pytest.raises(AttributeError):
            alert.plugin_id = "Y"  # type: ignore