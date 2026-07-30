"""健康检查引擎单元测试。"""


import asyncio

import pytest

from src.core.service_manager.health_check import HealthCheckEngine
from src.core.service_manager.types import (
    FaultReason,
    HealthCheckMode,
    HealthCheckResult,
    ServiceDescriptor,
    ServiceState,
    ServiceStateSnapshot,
)


def _make_descriptor(
    cid: str,
    mode: HealthCheckMode = HealthCheckMode.ACTIVE_PROBE,
    interval: int = 30,
) -> ServiceDescriptor:
    return ServiceDescriptor(
        identifier=cid,
        display_name=cid,
        health_mode=mode,
        check_interval_sec=interval,
    )


def _make_snapshot(
    cid: str, state: ServiceState = ServiceState.RUNNING
) -> ServiceStateSnapshot:
    return ServiceStateSnapshot(
        identifier=cid,
        display_name=cid,
        state=state,
        health_mode=HealthCheckMode.ACTIVE_PROBE,
    )


class TestProbeOne:
    """主动探测测试。"""

    @pytest.mark.asyncio
    async def test_probe_alive_resets_failures(self) -> None:
        registry = {"test": _make_snapshot("test")}
        descriptors = {"test": _make_descriptor("test")}
        probe_fns = {"test": lambda: asyncio.sleep(0, result=HealthCheckResult(True, 0))}
        faults: list[tuple] = []

        engine = HealthCheckEngine(
            registry, descriptors, probe_fns, lambda *a: faults.append(a)
        )
        engine._consecutive_failures["test"] = 1

        await engine._probe_one("test")
        assert "test" not in engine._consecutive_failures

    @pytest.mark.asyncio
    async def test_probe_dead_increments_failures(self) -> None:
        registry = {"test": _make_snapshot("test")}
        descriptors = {"test": _make_descriptor("test")}
        probe_fns = {"test": lambda: asyncio.sleep(0, result=HealthCheckResult(False, 0, "down"))}
        faults: list[tuple] = []

        engine = HealthCheckEngine(
            registry, descriptors, probe_fns, lambda *a: faults.append(a)
        )
        await engine._probe_one("test")
        assert engine._consecutive_failures.get("test") == 1
        assert len(faults) == 0  # 未达阈值

    @pytest.mark.asyncio
    async def test_consecutive_failures_trigger_callback(self) -> None:
        registry = {"test": _make_snapshot("test")}
        descriptors = {"test": _make_descriptor("test")}
        probe_fns = {"test": lambda: asyncio.sleep(0, result=HealthCheckResult(False, 0, "down"))}
        faults: list[tuple] = []

        async def fault_cb(cid: str, reason: FaultReason, detail: str) -> None:
            faults.append((cid, reason, detail))

        engine = HealthCheckEngine(
            registry, descriptors, probe_fns, fault_cb, consecutive_fail_threshold=2
        )
        await engine._probe_one("test")
        await engine._probe_one("test")
        assert len(faults) == 1
        assert faults[0][0] == "test"
        assert "test" not in engine._consecutive_failures  # 重置

    @pytest.mark.asyncio
    async def test_probe_exception_counts_as_failure(self) -> None:
        registry = {"test": _make_snapshot("test")}
        descriptors = {"test": _make_descriptor("test")}

        async def bad_probe() -> HealthCheckResult:
            raise RuntimeError("探针异常")

        faults: list[tuple] = []
        engine = HealthCheckEngine(
            registry, descriptors, {"test": bad_probe}, lambda *a: faults.append(a)
        )
        await engine._probe_one("test")
        assert engine._consecutive_failures.get("test") == 1

    @pytest.mark.asyncio
    async def test_skip_stopped_component(self) -> None:
        registry = {"test": _make_snapshot("test", ServiceState.STOPPED)}
        descriptors = {"test": _make_descriptor("test")}
        called: list[str] = []

        async def probe() -> HealthCheckResult:
            called.append("probe")
            return HealthCheckResult(True, 0)

        engine = HealthCheckEngine(
            registry, descriptors, {"test": probe}, lambda *a: None
        )
        await engine._probe_one("test")
        assert len(called) == 0  # 未调用探针


class TestHeartbeat:
    """被动心跳测试。"""

    def test_report_heartbeat(self) -> None:
        registry = {"test": _make_snapshot("test")}
        engine = HealthCheckEngine(registry, {}, {}, lambda *a: None)
        engine.report_heartbeat("test", 100.0)
        assert engine._last_heartbeats["test"] == 100.0

    def test_heartbeat_backwards_ignored(self) -> None:
        registry = {"test": _make_snapshot("test")}
        engine = HealthCheckEngine(registry, {}, {}, lambda *a: None)
        engine.report_heartbeat("test", 100.0)
        engine.report_heartbeat("test", 50.0)  # 回跳
        assert engine._last_heartbeats["test"] == 100.0

    def test_heartbeat_duplicate_ignored(self) -> None:
        registry = {"test": _make_snapshot("test")}
        engine = HealthCheckEngine(registry, {}, {}, lambda *a: None)
        engine.report_heartbeat("test", 100.0)
        engine.report_heartbeat("test", 100.0)  # 重复
        assert engine._last_heartbeats["test"] == 100.0


class TestRunLoop:
    """主循环测试。"""

    @pytest.mark.asyncio
    async def test_stop_event_exits(self) -> None:
        registry = {"test": _make_snapshot("test")}
        descriptors = {"test": _make_descriptor("test", interval=5)}

        async def probe() -> HealthCheckResult:
            return HealthCheckResult(True, 0)

        engine = HealthCheckEngine(
            registry, descriptors, {"test": probe}, lambda *a: None
        )
        stop_event = asyncio.Event()
        stop_event.set()
        await engine.run_loop(stop_event)  # 应立即退出