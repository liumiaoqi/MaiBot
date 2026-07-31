"""Suppressor + 健康等级接入点单元测试（ZG-2 T-05）。

覆盖：四级策略表映射（AC-SUP-02-1）、豁免组件（AC-SUP-03-2）、防抖、
注入自定义策略生效（AC-STT-01-1）、未注入用默认（AC-STT-01-2）、
回调异常回退 HEALTHY（AC-STT-02-2）。
"""

import logging
import time

import pytest

from src.common.log_pipeline.suppressor import (
    Suppressor,
    _get_current_health_level,
    set_health_level_provider,
)

HEALTH_MAP = {
    "healthy": "none",
    "degraded": "INFO",
    "fault": "WARNING",
    "recovering": "INFO",
}


def _make_suppressor(debounce_s: float = 0.0) -> Suppressor:
    return Suppressor(HEALTH_MAP, ("service_manager", "watchdog"), debounce_s)


def test_level_map_mapping():
    """AC-SUP-02-1: 四级策略表映射（枚举映射可单测）。"""
    s = _make_suppressor()
    s.set_health_level("healthy")
    assert s.current_threshold() == 0
    s.set_health_level("degraded")
    assert s.current_threshold() == logging.INFO
    s.set_health_level("fault")
    assert s.current_threshold() == logging.WARNING
    s.set_health_level("recovering")
    assert s.current_threshold() == logging.INFO


def test_degraded_suppresses_debug_only():
    """AC-SUP-01-1: DEGRADED 时 DEBUG 抑制，WARNING 正常。"""
    s = _make_suppressor()
    s.set_health_level("degraded")
    assert s.should_suppress(logging.DEBUG, "some.module") is True
    assert s.should_suppress(logging.INFO, "some.module") is False
    assert s.should_suppress(logging.WARNING, "some.module") is False


def test_fault_suppresses_debug_info():
    """AC-SUP-01-2: FAULT 时 DEBUG+INFO 抑制，ERROR 始终输出。"""
    s = _make_suppressor()
    s.set_health_level("fault")
    assert s.should_suppress(logging.DEBUG, "some.module") is True
    assert s.should_suppress(logging.INFO, "some.module") is True
    assert s.should_suppress(logging.ERROR, "some.module") is False
    assert s.should_suppress(logging.CRITICAL, "some.module") is False


def test_exempt_components():
    """AC-SUP-03-2: FAULT 时 watchdog 故障判定 WARNING 不抑制（诊断路径豁免）。"""
    s = _make_suppressor()
    s.set_health_level("fault")
    # 豁免组件：WARNING 判定日志不抑制（诊断路径豁免）
    assert s.should_suppress(logging.WARNING, "watchdog.event_loop_monitor") is False
    assert s.should_suppress(logging.WARNING, "service_manager.health_check") is False
    # 豁免组件：即使 DEBUG 也豁免（组件整体豁免）
    assert s.should_suppress(logging.DEBUG, "watchdog.event_loop_monitor") is False
    # 非豁免组件：FAULT 下 WARNING 及以上放行（抑制线=WARNING），DEBUG 被抑制
    assert s.should_suppress(logging.WARNING, "some.other.module") is False
    assert s.should_suppress(logging.DEBUG, "some.other.module") is True


def test_debounce():
    """防抖：健康等级切换最小间隔生效。"""
    s = _make_suppressor(debounce_s=5.0)
    s.set_health_level("healthy")
    s.set_health_level("fault")
    assert s.current_threshold() == 0  # 防抖期内保持 healthy

    # 模拟防抖期过后
    s._last_switch = time.monotonic() - 6.0
    s.set_health_level("fault")
    assert s.current_threshold() == logging.WARNING


def test_provider_injection_takes_effect():
    """AC-STT-01-1: 注入自定义策略生效。"""
    set_health_level_provider(lambda: type("L", (), {"value": "fault"})())
    assert _get_current_health_level() == "fault"
    set_health_level_provider(None)  # 清理


def test_no_provider_defaults_healthy():
    """AC-STT-01-2: 未注入 provider 时用默认 HEALTHY。"""
    set_health_level_provider(None)
    assert _get_current_health_level() == "healthy"


def test_provider_exception_falls_back():
    """AC-STT-02-2: provider 回调异常回退 HEALTHY，不影响日志输出。"""
    def bad_provider() -> object:
        raise RuntimeError("boom")

    set_health_level_provider(bad_provider)
    assert _get_current_health_level() == "healthy"
    set_health_level_provider(None)
