"""ZG16-6a: 配置测试——bot_config.toml + AppConfigPort 默认值。

覆盖 design 4.9 全部 6 个场景。
"""

from unittest.mock import MagicMock

from src.core.adapters.app_config_port import GlobalConfigAppConfigPort


def _make_port_with_config(config=None):
    """构造 GlobalConfigAppConfigPort，config 为 None 时走默认值。

    config 是 plugin_runtime_v2 子配置对象（含 plugin_config_debounce_ms 等字段）。
    """
    port = GlobalConfigAppConfigPort()
    global_config = MagicMock()
    if config is not None:
        global_config.plugin_runtime_v2 = config
    else:
        # 无 plugin_runtime_v2 节 → 走默认值
        global_config.plugin_runtime_v2 = None
    port._get_cfg = MagicMock(return_value=global_config)
    return port


def test_debounce_default_300():
    """debounce 默认 300（spec 4.1.3）。"""
    port = _make_port_with_config()
    assert port.get_plugin_config_debounce_ms() == 300


def test_debounce_custom():
    """debounce 自定义值。"""
    cfg = MagicMock()
    cfg.plugin_config_debounce_ms = 500
    port = _make_port_with_config(cfg)
    assert port.get_plugin_config_debounce_ms() == 500


def test_revision_path_default():
    """revision 路径默认。"""
    port = _make_port_with_config()
    assert port.get_plugin_config_revision_path() == "data/plugin_runtime_v2/plugin_config_revisions.json"


def test_revision_path_custom():
    """revision 路径自定义。"""
    cfg = MagicMock()
    cfg.plugin_config_revision_path = "custom/rev.json"
    port = _make_port_with_config(cfg)
    assert port.get_plugin_config_revision_path() == "custom/rev.json"


def test_watch_default_true():
    """watch 开关默认 true。"""
    port = _make_port_with_config()
    assert port.get_enable_plugin_config_watch() is True


def test_watch_custom_false():
    """watch 开关自定义 false。"""
    cfg = MagicMock()
    cfg.enable_plugin_config_watch = False
    port = _make_port_with_config(cfg)
    assert port.get_enable_plugin_config_watch() is False


def test_dump_default_true():
    """dump 开关默认 true。"""
    port = _make_port_with_config()
    assert port.get_enable_dump_plugin_config() is True


def test_dump_custom_false():
    """dump 开关自定义 false。"""
    cfg = MagicMock()
    cfg.enable_dump_plugin_config = False
    port = _make_port_with_config(cfg)
    assert port.get_enable_dump_plugin_config() is False


def test_drift_detect_default_true():
    """漂移检测开关默认 true。"""
    port = _make_port_with_config()
    assert port.get_enable_schema_drift_detect() is True


def test_drift_detect_custom_false():
    """漂移检测开关自定义 false。"""
    cfg = MagicMock()
    cfg.enable_schema_drift_detect = False
    port = _make_port_with_config(cfg)
    assert port.get_enable_schema_drift_detect() is False


def test_get_plugin_override_no_config():
    """get_plugin_override 无 bot_config → 返回 ({}, {})。"""
    port = _make_port_with_config()
    result = port.get_plugin_override("X")
    assert result == ({}, {})


def test_debounce_range_positive():
    """debounce 值为正整数。"""
    port = _make_port_with_config()
    debounce = port.get_plugin_config_debounce_ms()
    assert isinstance(debounce, int)
    assert debounce > 0