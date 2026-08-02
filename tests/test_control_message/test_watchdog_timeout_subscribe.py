"""T13 WatchdogPort.subscribe_timeout 测试 — 超时事件订阅转发。"""


import pytest

from src.core.adapters.watchdog_adapter import WatchdogAdapter
from src.core.watchdog.config import WatchdogConfig
from src.core.watchdog.types import FaultReason, FaultReportEvent


class TestSubscribeTimeout:
    def _make_adapter(self) -> WatchdogAdapter:
        return WatchdogAdapter(config=WatchdogConfig())

    def test_subscribe_and_notify(self) -> None:
        """订阅超时事件：故障上报路径同步通知已注册回调（spec §7.4 衔接）。"""
        adapter = self._make_adapter()
        received: list[FaultReportEvent] = []

        def handler(event: FaultReportEvent) -> None:
            received.append(event)

        adapter.subscribe_timeout(handler)
        event = FaultReportEvent(
            component_id="component:runner_a",
            reason=FaultReason.RUNNER_UNRESPONSIVE,
            detail="runner heartbeat timeout",
            report_time=100.0,
            check_period_no=5,
        )
        adapter._notify_timeout_subscribers(event)
        assert len(received) == 1
        assert received[0].component_id == "component:runner_a"
        assert received[0].reason is FaultReason.RUNNER_UNRESPONSIVE

    def test_unsubscribe(self) -> None:
        adapter = self._make_adapter()
        received: list[FaultReportEvent] = []

        def handler(event: FaultReportEvent) -> None:
            received.append(event)

        adapter.subscribe_timeout(handler)
        adapter.unsubscribe_timeout(handler)
        event = FaultReportEvent(
            component_id="c1", reason=FaultReason.LOOP_BLOCKED, detail="", report_time=100.0, check_period_no=5
        )
        adapter._notify_timeout_subscribers(event)
        assert received == []

    def test_no_subscribers_no_error(self) -> None:
        adapter = self._make_adapter()
        event = FaultReportEvent(
            component_id="c1", reason=FaultReason.LOOP_BLOCKED, detail="", report_time=100.0, check_period_no=5
        )
        adapter._notify_timeout_subscribers(event)  # 不抛错

    @pytest.mark.asyncio
    async def test_report_path_notifies(self) -> None:
        """_do_report（故障上报路径）触发超时通知。"""
        adapter = self._make_adapter()
        received: list[FaultReportEvent] = []
        adapter.subscribe_timeout(lambda e: received.append(e))
        event = FaultReportEvent(
            component_id="c1", reason=FaultReason.LOOP_BLOCKED, detail="loop stuck", report_time=100.0, check_period_no=5
        )
        await adapter._do_report(event)
        assert len(received) == 1
        assert received[0].detail == "loop stuck"

    def test_subscriber_error_isolation(self) -> None:
        """订阅回调异常不影响其他订阅者。"""
        adapter = self._make_adapter()
        received: list[FaultReportEvent] = []

        def bad_handler(event: FaultReportEvent) -> None:
            raise RuntimeError("boom")

        def good_handler(event: FaultReportEvent) -> None:
            received.append(event)

        adapter.subscribe_timeout(bad_handler)
        adapter.subscribe_timeout(good_handler)
        event = FaultReportEvent(
            component_id="c1", reason=FaultReason.RUNNER_UNRESPONSIVE, detail="", report_time=100.0, check_period_no=5
        )
        adapter._notify_timeout_subscribers(event)
        assert len(received) == 1
