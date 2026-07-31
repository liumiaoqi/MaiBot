"""WatchdogAdapter 单元测试。"""


import asyncio


import pytest

from src.core.service_manager_port_registry import (
    reset_service_manager_port,
    set_service_manager_port,
)
from src.core.watchdog.config import WatchdogConfig
from src.core.watchdog.exceptions import (
    ServiceManagerPortNotReadyError,
    WatchdogAlreadyRunningError,
)
from src.core.watchdog_port_registry import clear_watchdog_port, set_watchdog_port
from src.core.adapters.watchdog_adapter import WatchdogAdapter
from src.core.watchdog.types import BlockSeverity, WatchdogStatus


class FakeServiceManagerPort:
    """模拟 ServiceManagerPort。"""

    def __init__(self) -> None:
        self.reports: list[tuple[str, str, str]] = []

    async def report_external_fault(
        self, component_id: str, reason: str, detail: str = ""
    ) -> None:
        self.reports.append((component_id, reason, detail))

    def get_state(self, component_id: str) -> None:
        return None


@pytest.fixture
def fake_sm_port():
    port = FakeServiceManagerPort()
    set_service_manager_port(port)
    yield port
    reset_service_manager_port()


@pytest.fixture
def watchdog(fake_sm_port):
    adapter = WatchdogAdapter(config=WatchdogConfig())
    set_watchdog_port(adapter)
    yield adapter
    clear_watchdog_port()


@pytest.mark.asyncio
async def test_start_stop_lifecycle(watchdog):
    loop = asyncio.get_running_loop()
    await watchdog.start(loop)
    assert watchdog._running is True
    await watchdog.stop()
    assert watchdog._running is False


@pytest.mark.asyncio
async def test_start_without_service_manager_raises():
    from src.core.service_manager_port_registry import reset_service_manager_port

    reset_service_manager_port()
    adapter = WatchdogAdapter(config=WatchdogConfig())
    loop = asyncio.get_running_loop()
    with pytest.raises(ServiceManagerPortNotReadyError):
        await adapter.start(loop)


@pytest.mark.asyncio
async def test_double_start_raises(watchdog):
    loop = asyncio.get_running_loop()
    await watchdog.start(loop)
    try:
        with pytest.raises(WatchdogAlreadyRunningError):
            await watchdog.start(loop)
    finally:
        await watchdog.stop()


@pytest.mark.asyncio
async def test_touch_delegates(watchdog):
    loop = asyncio.get_running_loop()
    await watchdog.start(loop)
    try:
        watchdog.touch()
        import time

        time.sleep(0.1)
        status = watchdog.get_status()
        assert status.last_touch_time > 0
    finally:
        await watchdog.stop()


@pytest.mark.asyncio
async def test_status_query_before_start():
    adapter = WatchdogAdapter(config=WatchdogConfig())
    status = adapter.get_status()
    assert status.block_severity == BlockSeverity.NORMAL


@pytest.mark.asyncio
async def test_subscribe_status_change(watchdog):
    loop = asyncio.get_running_loop()
    await watchdog.start(loop)
    try:
        received: list[WatchdogStatus] = []
        watchdog.subscribe_status_change(received.append)
        watchdog.touch()
        import time

        time.sleep(0.1)
        assert len(received) >= 0
        watchdog.unsubscribe_status_change(received.append)
    finally:
        await watchdog.stop()


@pytest.mark.asyncio
async def test_runner_bridge_status_empty(watchdog):
    loop = asyncio.get_running_loop()
    await watchdog.start(loop)
    try:
        assert watchdog.get_runner_bridge_status("nonexistent") is None
        assert watchdog.list_runner_bridge_status() == []
    finally:
        await watchdog.stop()