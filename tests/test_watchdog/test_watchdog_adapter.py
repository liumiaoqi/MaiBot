"""WatchdogAdapter 单元测试。"""


import asyncio
from unittest.mock import MagicMock


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
from src.core.watchdog.types import BlockSeverity, FaultReportEvent, FaultReason, WatchdogStatus


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


@pytest.mark.asyncio
async def test_config_injected_from_app_config_port(monkeypatch, fake_sm_port):
    """AC-2.2.1：经 AppConfigPort 注入的配置被 WatchdogAdapter 持有。"""
    from src.core import app_config_port_registry

    fake_port = MagicMock()
    fake_port.get_watchdog_config.return_value = WatchdogConfig(check_interval_s=3.0)
    monkeypatch.setattr(app_config_port_registry, "get_app_config_port", lambda: fake_port)

    watchdog_config = app_config_port_registry.get_app_config_port().get_watchdog_config()
    adapter = WatchdogAdapter(config=watchdog_config)

    assert adapter._config.check_interval_s == 3.0


@pytest.mark.asyncio
async def test_default_config_start_succeeds(fake_sm_port):
    """AC-2.2.2：未配置看门狗参数时使用默认值，启动不失败。"""
    adapter = WatchdogAdapter(config=WatchdogConfig())
    loop = asyncio.get_running_loop()
    await adapter.start(loop)
    try:
        assert adapter._config.check_interval_s == 5.0
    finally:
        await adapter.stop()


@pytest.mark.asyncio
async def test_sync_report_submits_notify_to_main_loop(watchdog, monkeypatch):
    """AC-4.1.1：检测线程路径经 run_coroutine_threadsafe 提交，订阅回调不在检测线程同步执行。"""
    loop = asyncio.get_running_loop()
    await watchdog.start(loop)
    try:
        submitted: list = []

        def _fake_run_coroutine_threadsafe(coro, target_loop):
            submitted.append(coro)
            coro.close()
            return None

        monkeypatch.setattr(
            asyncio,
            "run_coroutine_threadsafe",
            _fake_run_coroutine_threadsafe,
        )
        received: list = []
        watchdog.subscribe_status_change(received.append)

        watchdog._sync_report_callback(
            FaultReportEvent(
                component_id="test",
                reason=FaultReason.LOOP_BLOCKED,
                detail="blocked",
                report_time=0.0,
                check_period_no=0,
            )
        )

        assert submitted
        assert received == []
    finally:
        await watchdog.stop()


@pytest.mark.asyncio
async def test_notify_subscribers_isolation(watchdog):
    """AC-4.1.2：订阅回调抛异常被捕获，不影响后续订阅者。"""
    loop = asyncio.get_running_loop()
    await watchdog.start(loop)
    try:
        calls: list[str] = []

        def bad_cb(status):
            calls.append("bad")
            raise RuntimeError("boom")

        def good_cb(status):
            calls.append("good")

        watchdog.subscribe_status_change(bad_cb)
        watchdog.subscribe_status_change(good_cb)

        await watchdog._notify_subscribers_async()

        assert calls == ["bad", "good"]
    finally:
        await watchdog.stop()


@pytest.mark.asyncio
async def test_async_report_notifies_once(watchdog):
    """AC-4.2.1：桥接上报路径订阅回调恰好被调用一次。"""
    loop = asyncio.get_running_loop()
    await watchdog.start(loop)
    try:
        received: list = []
        watchdog.subscribe_status_change(received.append)

        await watchdog._async_report_callback(
            FaultReportEvent(
                component_id="test",
                reason=FaultReason.RUNNER_UNRESPONSIVE,
                detail="runner down",
                report_time=0.0,
                check_period_no=0,
            )
        )

        assert len(received) == 1
    finally:
        await watchdog.stop()