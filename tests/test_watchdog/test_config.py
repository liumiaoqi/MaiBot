"""WatchdogConfig 单元测试。"""


import pytest

from src.core.watchdog.config import WatchdogConfig


def test_default_config() -> None:
    c = WatchdogConfig()
    assert c.touch_interval_s == 1.0
    assert c.check_interval_s == 5.0
    assert c.mild_threshold_s == 3.0
    assert c.severe_threshold_s == 10.0
    assert c.consecutive_report_threshold == 2
    assert c.cooldown_s == 30.0
    assert c.v1_poll_interval_s == 10.0
    assert c.v2_diff_interval_s == 5.0


def test_severe_equals_mild_raises() -> None:
    with pytest.raises(ValueError, match="severe_threshold_s"):
        WatchdogConfig(severe_threshold_s=3.0, mild_threshold_s=3.0)


def test_severe_less_than_mild_raises() -> None:
    with pytest.raises(ValueError, match="severe_threshold_s"):
        WatchdogConfig(severe_threshold_s=2.0, mild_threshold_s=3.0)


def test_negative_touch_interval_raises() -> None:
    with pytest.raises(ValueError, match="touch_interval_s"):
        WatchdogConfig(touch_interval_s=-1)


def test_negative_check_interval_raises() -> None:
    with pytest.raises(ValueError, match="check_interval_s"):
        WatchdogConfig(check_interval_s=0)


def test_consecutive_threshold_zero_raises() -> None:
    with pytest.raises(ValueError, match="consecutive_report_threshold"):
        WatchdogConfig(consecutive_report_threshold=0)


def test_negative_cooldown_raises() -> None:
    with pytest.raises(ValueError, match="cooldown_s"):
        WatchdogConfig(cooldown_s=-5)