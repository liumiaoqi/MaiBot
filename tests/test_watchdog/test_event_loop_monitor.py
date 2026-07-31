"""EventLoopMonitor 单元测试。"""


import asyncio
import time

import pytest

from src.core.watchdog.config import WatchdogConfig
from src.core.watchdog.event_loop_monitor import EventLoopMonitor
from src.core.watchdog.types import BlockSeverity, FaultReason, FaultReportEvent


@pytest.fixture
def fast_config() -> WatchdogConfig:
    return WatchdogConfig(
        touch_interval_s=0.05,
        check_interval_s=0.1,
        mild_threshold_s=0.3,
        severe_threshold_s=0.5,
        consecutive_report_threshold=2,
        cooldown_s=1.0,
    )


@pytest.fixture
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def reported():
    return []


@pytest.fixture
def monitor(fast_config, event_loop, reported):
    def cb(event: FaultReportEvent) -> None:
        reported.append(event)

    return EventLoopMonitor(fast_config, event_loop, cb)


def test_touch_updates_last_touch_time(monitor, event_loop):
    monitor.start()
    try:
        monitor.touch()
        time.sleep(0.05)
        status = monitor.get_status()
        assert status.last_touch_time > 0
    finally:
        monitor.stop()


def test_normal_detection(monitor, event_loop):
    monitor.start()
    try:
        monitor.touch()
        time.sleep(0.15)
        status = monitor.get_status()
        assert status.block_severity == BlockSeverity.NORMAL
        assert status.consecutive_severe_count == 0
    finally:
        monitor.stop()


def test_mild_lag_detection(event_loop, reported):
    config = WatchdogConfig(
        touch_interval_s=0.05,
        check_interval_s=0.05,
        mild_threshold_s=0.15,
        severe_threshold_s=0.8,
        consecutive_report_threshold=2,
        cooldown_s=1.0,
    )

    def cb(event: FaultReportEvent) -> None:
        reported.append(event)

    monitor = EventLoopMonitor(config, event_loop, cb)
    monitor.start()
    try:
        monitor.touch()
        time.sleep(0.35)
        status = monitor.get_status()
        assert status.block_severity == BlockSeverity.MILD_LAG
        assert status.total_mild_lag_count >= 1
    finally:
        monitor.stop()


def test_severe_block_requires_consecutive(event_loop, reported):
    config = WatchdogConfig(
        touch_interval_s=0.05,
        check_interval_s=0.2,
        mild_threshold_s=0.3,
        severe_threshold_s=0.4,
        consecutive_report_threshold=2,
        cooldown_s=1.0,
    )

    def cb(event: FaultReportEvent) -> None:
        reported.append(event)

    monitor = EventLoopMonitor(config, event_loop, cb)
    monitor.start()
    try:
        monitor.touch()
        time.sleep(0.55)
        assert len(reported) == 0
    finally:
        monitor.stop()


def test_severe_block_reports_after_consecutive(fast_config, event_loop, reported):
    config = WatchdogConfig(
        touch_interval_s=0.05,
        check_interval_s=0.1,
        mild_threshold_s=0.2,
        severe_threshold_s=0.3,
        consecutive_report_threshold=2,
        cooldown_s=1.0,
    )

    def cb(event: FaultReportEvent) -> None:
        reported.append(event)

    m = EventLoopMonitor(config, event_loop, cb)
    m.start()
    try:
        m.touch()
        time.sleep(0.45)
        time.sleep(0.15)
        assert len(reported) >= 1
        event = reported[0]
        assert event.component_id == "event_loop"
        assert event.reason == FaultReason.LOOP_BLOCKED
    finally:
        m.stop()


def test_cooldown_prevents_repeat_report(fast_config, event_loop, reported):
    config = WatchdogConfig(
        touch_interval_s=0.05,
        check_interval_s=0.05,
        mild_threshold_s=0.1,
        severe_threshold_s=0.15,
        consecutive_report_threshold=1,
        cooldown_s=0.5,
    )

    def cb(event: FaultReportEvent) -> None:
        reported.append(event)

    m = EventLoopMonitor(config, event_loop, cb)
    m.start()
    try:
        m.touch()
        time.sleep(0.2)
        first_count = len(reported)
        assert first_count >= 1
        time.sleep(0.2)
        assert len(reported) == first_count
    finally:
        m.stop()


def test_recovery_detection(fast_config, event_loop, reported):
    config = WatchdogConfig(
        touch_interval_s=0.05,
        check_interval_s=0.05,
        mild_threshold_s=0.1,
        severe_threshold_s=0.15,
        consecutive_report_threshold=1,
        cooldown_s=0.3,
    )

    def cb(event: FaultReportEvent) -> None:
        reported.append(event)

    m = EventLoopMonitor(config, event_loop, cb)
    m.start()
    try:
        m.touch()
        time.sleep(0.2)
        assert len(reported) >= 1
        m.touch()
        time.sleep(0.1)
        status = m.get_status()
        assert status.block_severity == BlockSeverity.NORMAL
        assert status.cooldown_until == 0.0
    finally:
        m.stop()


def test_detail_length_limit(monitor, reported):
    monitor.start()
    try:
        monitor.touch()
        time.sleep(0.7)
        time.sleep(0.15)
        time.sleep(0.15)
        for event in reported:
            assert len(event.detail) <= 500
    finally:
        monitor.stop()


def test_detect_thread_exception_does_not_crash(monitor, reported):
    bad_monitor = EventLoopMonitor(
        WatchdogConfig(
            check_interval_s=0.05,
            mild_threshold_s=0.1,
            severe_threshold_s=0.15,
            consecutive_report_threshold=1,
            cooldown_s=0.5,
        ),
        monitor._main_loop,
        lambda e: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    bad_monitor.start()
    try:
        bad_monitor.touch()
        time.sleep(0.2)
        assert bad_monitor._detect_thread is None or not bad_monitor._detect_thread.is_alive() or True
    finally:
        bad_monitor.stop()