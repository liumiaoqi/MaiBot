"""数据模型单元测试。"""


import pytest

from src.core.watchdog.types import (
    BlockSeverity,
    DetectionSource,
    FaultReason,
    FaultReportEvent,
    RunnerBridgeStatus,
    WatchdogStatus,
)


def test_block_severity_values() -> None:
    assert BlockSeverity.NORMAL == "normal"
    assert BlockSeverity.MILD_LAG == "mild_lag"
    assert BlockSeverity.SEVERE_BLOCK == "severe_block"


def test_detection_source_values() -> None:
    assert DetectionSource.HEARTBEAT == "heartbeat"
    assert DetectionSource.PROCESS_POLL == "process_poll"
    assert DetectionSource.REGISTRY == "registry"


def test_fault_reason_values() -> None:
    assert FaultReason.LOOP_BLOCKED == "loop_blocked"
    assert FaultReason.RUNNER_UNRESPONSIVE == "runner_unresponsive"


def test_fault_report_event_detail_too_long() -> None:
    with pytest.raises(ValueError, match="500"):
        FaultReportEvent(
            component_id="test",
            reason=FaultReason.LOOP_BLOCKED,
            detail="x" * 501,
            report_time=0.0,
            check_period_no=0,
        )


def test_fault_report_event_detail_boundary() -> None:
    event = FaultReportEvent(
        component_id="test",
        reason=FaultReason.LOOP_BLOCKED,
        detail="x" * 500,
        report_time=0.0,
        check_period_no=0,
    )
    assert len(event.detail) == 500


def test_watchdog_status_frozen() -> None:
    status = WatchdogStatus(
        block_severity=BlockSeverity.NORMAL,
        last_touch_time=0.0,
        last_check_time=0.0,
        consecutive_severe_count=0,
        cooldown_until=0.0,
        total_mild_lag_count=0,
        total_severe_report_count=0,
        check_period_no=0,
    )
    with pytest.raises(AttributeError):
        status.block_severity = BlockSeverity.MILD_LAG  # type: ignore[misc]


def test_runner_bridge_status_frozen() -> None:
    status = RunnerBridgeStatus(
        runner_id="r1",
        component_id="c1",
        last_detection_source=DetectionSource.HEARTBEAT,
        last_consecutive_failures=0,
        cooldown_until=0.0,
        total_report_count=0,
        last_report_time=0.0,
        is_recovering=False,
    )
    with pytest.raises(AttributeError):
        status.is_recovering = True  # type: ignore[misc]