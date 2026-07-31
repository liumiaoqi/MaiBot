"""GlobalConfigAppConfigPort.get_watchdog_config 单元测试（FR-2 配置 Port）。"""


from types import SimpleNamespace

import pytest

from src.core.adapters.app_config_port import GlobalConfigAppConfigPort
from src.core.watchdog.config import WatchdogConfig


def _make_watchdog_section(**overrides):
    """构造 [watchdog] 配置域对象，缺省回落默认值。"""
    defaults = dict(
        touch_interval_s=1.0,
        check_interval_s=5.0,
        mild_threshold_s=3.0,
        severe_threshold_s=10.0,
        consecutive_report_threshold=2,
        cooldown_s=30.0,
        v1_poll_interval_s=10.0,
        v2_diff_interval_s=5.0,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_port(monkeypatch, section=None):
    """构造适配器并替换配置源，返回 (port, section)。"""
    port = GlobalConfigAppConfigPort()
    section = section if section is not None else _make_watchdog_section()
    monkeypatch.setattr(port, "_get_cfg", lambda: SimpleNamespace(watchdog=section))
    return port


def test_get_watchdog_config_matches_configured_values(monkeypatch):
    """AC-2.1.1：配置文件设置看门狗参数后，返回值与配置一致。"""
    section = _make_watchdog_section(
        check_interval_s=3.0,
        severe_threshold_s=12.0,
        consecutive_report_threshold=3,
        v2_diff_interval_s=7.0,
    )
    port = _make_port(monkeypatch, section)

    cfg = port.get_watchdog_config()

    assert cfg == WatchdogConfig(
        touch_interval_s=1.0,
        check_interval_s=3.0,
        mild_threshold_s=3.0,
        severe_threshold_s=12.0,
        consecutive_report_threshold=3,
        cooldown_s=30.0,
        v1_poll_interval_s=10.0,
        v2_diff_interval_s=7.0,
    )


def test_get_watchdog_config_defaults(monkeypatch):
    """AC-2.1.2：默认配置回落 WatchdogConfig 默认值。"""
    port = _make_port(monkeypatch)

    assert port.get_watchdog_config() == WatchdogConfig()


def test_get_watchdog_config_invalid_ratio_raises(monkeypatch):
    """数据约束 4：severe_threshold_s 不大于 mild_threshold_s 时抛中文 ValueError。"""
    section = _make_watchdog_section(severe_threshold_s=3.0, mild_threshold_s=3.0)
    port = _make_port(monkeypatch, section)

    with pytest.raises(ValueError, match="必须大于"):
        port.get_watchdog_config()


def test_get_watchdog_config_negative_interval_raises(monkeypatch):
    """数据约束 4：负间隔抛中文 ValueError。"""
    section = _make_watchdog_section(touch_interval_s=-1.0)
    port = _make_port(monkeypatch, section)

    with pytest.raises(ValueError, match="必须为正数"):
        port.get_watchdog_config()


def test_get_watchdog_config_low_n_raises(monkeypatch):
    """数据约束 4：consecutive_report_threshold < 1 抛中文 ValueError。"""
    section = _make_watchdog_section(consecutive_report_threshold=0)
    port = _make_port(monkeypatch, section)

    with pytest.raises(ValueError, match="必须 >= 1"):
        port.get_watchdog_config()