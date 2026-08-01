"""test_watchdog 共享 fixture（ZG-3 补强时抽离，消除 4 个测试文件重复）。

既有测试文件内的同名 fixture 优先于本 conftest（pytest 局部优先），不受影响。
"""


import asyncio

import pytest

from src.core.watchdog.config import WatchdogConfig


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
    from src.core.watchdog.event_loop_monitor import EventLoopMonitor
    from src.core.watchdog.types import FaultReportEvent

    def cb(event: FaultReportEvent) -> None:
        reported.append(event)

    return EventLoopMonitor(fast_config, event_loop, cb)
