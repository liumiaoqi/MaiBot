"""S4 blocker 追踪测试（ZG-3 补强，对标 Linux CONFIG_DETECT_HUNG_TASK_BLOCKER）。

FaultReportEvent 新增可选 blocker_info：长度 ≤ 200、不含敏感数据（FR-S4-03/04）；
RunnerHealthBridge 按 DetectionSource 填充；EventLoopMonitor 事件循环侧为 None。
"""


import time

import pytest

from src.core.watchdog.event_loop_monitor import EventLoopMonitor
from src.core.watchdog.runner_health_bridge import RunnerHealthBridge
from src.core.watchdog.types import (
    DetectionSource,
    FaultReason,
    FaultReportEvent,
    RunnerBridgeStatus,
)


def test_blocker_info_in_fault_event():
    """tasks 5.1.1: blocker_info 正确存储。"""
    event = FaultReportEvent(
        component_id="event_loop",
        reason=FaultReason.LOOP_BLOCKED,
        detail="d",
        report_time=0.0,
        check_period_no=0,
        blocker_info="llm_sync_call",
    )
    assert event.blocker_info == "llm_sync_call"


def test_blocker_info_none_default():
    """tasks 5.1.2: 未传入 blocker_info 时默认为 None（向后兼容）。"""
    event = FaultReportEvent(
        component_id="x",
        reason=FaultReason.LOOP_BLOCKED,
        detail="d",
        report_time=0.0,
        check_period_no=0,
    )
    assert event.blocker_info is None


def test_blocker_info_length_limit():
    """tasks 5.1.3: 长度 > 200 抛 ValueError。"""
    with pytest.raises(ValueError):
        FaultReportEvent(
            component_id="x",
            reason=FaultReason.LOOP_BLOCKED,
            detail="d",
            report_time=0.0,
            check_period_no=0,
            blocker_info="x" * 201,
        )


def test_blocker_info_sensitive_reject():
    """tasks 5.1.4: 含敏感数据抛 ValueError（FR-S4-03）。"""
    for sensitive in ("sk-xxxx", "Key-Abc123", "TOKEN_abc"):
        with pytest.raises(ValueError):
            FaultReportEvent(
                component_id="x",
                reason=FaultReason.LOOP_BLOCKED,
                detail="d",
                report_time=0.0,
                check_period_no=0,
                blocker_info=sensitive,
            )


def _fresh_status() -> RunnerBridgeStatus:
    """无冷却状态的 RunnerBridgeStatus（每次上报前重置冷却窗口）。"""
    return RunnerBridgeStatus(
        runner_id="r1",
        component_id="plugin_runtime_v2",
        last_detection_source=DetectionSource.HEARTBEAT,
        last_consecutive_failures=1,
        cooldown_until=0.0,
        total_report_count=0,
        last_report_time=0.0,
        is_recovering=False,
    )


async def test_runner_unresponsive_blocker_info(fast_config, event_loop, monkeypatch):
    """tasks 5.1.5: Runner 无响应上报时 blocker_info 按 DetectionSource 填充。"""
    reported: list[FaultReportEvent] = []

    async def cb(event: FaultReportEvent) -> None:
        reported.append(event)

    bridge = RunnerHealthBridge(fast_config, event_loop, cb)
    bridge._bridge_status["r1"] = _fresh_status()

    # mock ServiceManagerPort：组件已注册
    class FakeSM:
        def get_state(self, cid):
            return {"component_id": cid}

    monkeypatch.setattr(
        "src.core.watchdog.runner_health_bridge.get_service_manager_port",
        lambda: FakeSM(),
    )

    # 每次上报前重置冷却窗口（上报后进入 cooldown_s=1.0，避免限流拦截）
    await bridge._report_runner_unresponsive("r1", DetectionSource.HEARTBEAT, 3)
    assert len(reported) == 1
    assert reported[0].blocker_info == "heartbeat_timeout"
    assert "blocker_info=heartbeat_timeout" in reported[0].detail

    reported.clear()
    bridge._bridge_status["r1"] = _fresh_status()
    await bridge._report_runner_unresponsive("r1", DetectionSource.PROCESS_POLL, 3)
    assert reported[0].blocker_info == "process_unresponsive"

    reported.clear()
    bridge._bridge_status["r1"] = _fresh_status()
    await bridge._report_runner_unresponsive("r1", DetectionSource.REGISTRY, 3)
    assert reported[0].blocker_info == "registry_connection_failed"


def test_event_loop_blocker_info_default_none(fast_config, event_loop):
    """tasks 5.1.6: 事件循环阻塞上报时 blocker_info 为 None。"""
    reported: list[FaultReportEvent] = []

    def cb(event: FaultReportEvent) -> None:
        reported.append(event)

    monitor = EventLoopMonitor(fast_config, event_loop, cb)
    monitor._last_touch_time = time.monotonic() - 10.0  # 严重阻塞
    monitor._detect_once()  # 周期 1 count=1
    monitor._detect_once()  # 周期 2 count=2 ≥ 2 → 上报
    assert len(reported) == 1
    assert reported[0].blocker_info is None
    assert "blocker_info=None" in reported[0].detail
