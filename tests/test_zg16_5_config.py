"""ZG16-5: AppConfigPort 审计配置 getter 测试。

验证 6 个审计配置项的默认值（未配置时返回默认值）。
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.core.adapters.app_config_port import GlobalConfigAppConfigPort


@pytest.fixture
def port():
    return GlobalConfigAppConfigPort()


@pytest.fixture
def mock_cfg_no_v2():
    """模拟 global_config 无 plugin_runtime_v2 属性 → 走默认值。"""
    cfg = SimpleNamespace()
    return cfg


class TestEnableScopeAuditDefault:
    """enable_scope_audit 默认 True。"""

    def test_enable_scope_audit_default_true(self, port, mock_cfg_no_v2):
        with patch.object(port, "_get_cfg", return_value=mock_cfg_no_v2):
            assert port.get_enable_scope_audit() is True

    def test_enable_scope_audit_configured_false(self, port):
        cfg = SimpleNamespace(plugin_runtime_v2=SimpleNamespace(enable_scope_audit=False))
        with patch.object(port, "_get_cfg", return_value=cfg):
            assert port.get_enable_scope_audit() is False

    def test_enable_scope_audit_configured_true(self, port):
        cfg = SimpleNamespace(plugin_runtime_v2=SimpleNamespace(enable_scope_audit=True))
        with patch.object(port, "_get_cfg", return_value=cfg):
            assert port.get_enable_scope_audit() is True


class TestAuditLogPathDefault:
    """audit_log_path 默认值。"""

    def test_audit_log_path_default(self, port, mock_cfg_no_v2):
        with patch.object(port, "_get_cfg", return_value=mock_cfg_no_v2):
            assert port.get_audit_log_path() == "data/plugin_runtime_v2/scope_audit.log"

    def test_audit_log_path_configured(self, port):
        cfg = SimpleNamespace(
            plugin_runtime_v2=SimpleNamespace(audit_log_path="/custom/audit.log"),
        )
        with patch.object(port, "_get_cfg", return_value=cfg):
            assert port.get_audit_log_path() == "/custom/audit.log"


class TestAuditLogMaxSizeMbDefault:
    """audit_log_max_size_mb 默认 10。"""

    def test_audit_log_max_size_mb_default(self, port, mock_cfg_no_v2):
        with patch.object(port, "_get_cfg", return_value=mock_cfg_no_v2):
            assert port.get_audit_log_max_size_mb() == 10

    def test_audit_log_max_size_mb_configured(self, port):
        cfg = SimpleNamespace(
            plugin_runtime_v2=SimpleNamespace(audit_log_max_size_mb=50),
        )
        with patch.object(port, "_get_cfg", return_value=cfg):
            assert port.get_audit_log_max_size_mb() == 50


class TestAuditLogBackupCountDefault:
    """audit_log_backup_count 默认 5。"""

    def test_audit_log_backup_count_default(self, port, mock_cfg_no_v2):
        with patch.object(port, "_get_cfg", return_value=mock_cfg_no_v2):
            assert port.get_audit_log_backup_count() == 5

    def test_audit_log_backup_count_configured(self, port):
        cfg = SimpleNamespace(
            plugin_runtime_v2=SimpleNamespace(audit_log_backup_count=10),
        )
        with patch.object(port, "_get_cfg", return_value=cfg):
            assert port.get_audit_log_backup_count() == 10


class TestTier1ScopesDefault:
    """tier1_scopes 默认 6 个新 scope。"""

    EXPECTED_TIER1 = [
        "system:execute:cli",
        "system:read:screenshot",
        "system:read:location",
        "account:execute:operation",
        "finance:read:qr_code",
        "network:fetch:url",
    ]

    def test_tier1_scopes_default(self, port, mock_cfg_no_v2):
        with patch.object(port, "_get_cfg", return_value=mock_cfg_no_v2):
            scopes = port.get_tier1_scopes()
            assert scopes == self.EXPECTED_TIER1
            assert len(scopes) == 6

    def test_tier1_scopes_configured(self, port):
        custom = ["custom:scope:one"]
        cfg = SimpleNamespace(
            plugin_runtime_v2=SimpleNamespace(tier1_scopes=custom),
        )
        with patch.object(port, "_get_cfg", return_value=cfg):
            assert port.get_tier1_scopes() == custom


class TestSensitiveParamNamesDefault:
    """sensitive_param_names 默认 6 个敏感字段名。"""

    EXPECTED_SENSITIVE = ["token", "password", "secret", "api_key", "apikey", "credential"]

    def test_sensitive_param_names_default(self, port, mock_cfg_no_v2):
        with patch.object(port, "_get_cfg", return_value=mock_cfg_no_v2):
            names = port.get_sensitive_param_names()
            assert names == self.EXPECTED_SENSITIVE
            assert len(names) == 6

    def test_sensitive_param_names_configured(self, port):
        custom = ["my_secret"]
        cfg = SimpleNamespace(
            plugin_runtime_v2=SimpleNamespace(sensitive_param_names=custom),
        )
        with patch.object(port, "_get_cfg", return_value=cfg):
            assert port.get_sensitive_param_names() == custom