"""RunnerHealthBridge 桥接上报与注册幂等测试（FR-1 + FR-3）。

覆盖 AC-1.3.1 / AC-1.3.2 与 spec.md 数据约束 3（注册幂等）、注销监听器摘除。
"""


import asyncio

import pytest

from src.core.watchdog.config import WatchdogConfig
from src.core.watchdog.runner_health_bridge import RunnerHealthBridge
from src.core.watchdog.types import FaultReportEvent


class FakeServiceManager:
    """mock ServiceManagerPort：get_state 返回非 None 使管理检查通过。"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def get_state(self, component_id: str) -> object:
        return object()

    async def report_external_fault(
        self, component_id: str, reason: str, detail: str = ""
    ) -> None:
        self.calls.append((component_id, reason, detail))


class FakeHeartbeatManager:
    """mock HeartbeatManager：记录监听器注入/摘除。"""

    def __init__(self) -> None:
        self.added: list[tuple[str, object]] = []
        self.removed: list[tuple[str, object]] = []

    def add_timeout_listener(self, runner_id: str, listener: object) -> None:
        self.added.append((runner_id, listener))

    def remove_timeout_listener(self, runner_id: str, listener: object) -> None:
        self.removed.append((runner_id, listener))


class FakeSupervisor:
    """mock V2 supervisor：提供 get_health_status。"""

    def __init__(self, health: dict | None = None) -> None:
        self._health = health or {}

    def get_health_status(self) -> dict:
        return self._health


def _make_bridge() -> tuple[RunnerHealthBridge, list[FaultReportEvent]]:
    """构造 RunnerHealthBridge，report_callback 记录收到的 FaultReportEvent。

    注意：必须在 async 测试内调用（main_loop 取当前 running loop）。
    """
    received: list[FaultReportEvent] = []

    async def report_callback(event: FaultReportEvent) -> None:
        received.append(event)

    b = RunnerHealthBridge(
        config=WatchdogConfig(),
        main_loop=asyncio.get_running_loop(),
        report_callback=report_callback,
    )
    return b, received


@pytest.mark.asyncio
async def test_v2_timeout_bridges_report(monkeypatch: pytest.MonkeyPatch):
    """AC-1.3.1: 心跳超时经 _on_v2_timeout 桥接上报，component_id/reason/detail 正确。"""
    monkeypatch.setattr(
        "src.core.watchdog.runner_health_bridge.get_service_manager_port",
        lambda: FakeServiceManager(),
    )
    bridge, received = _make_bridge()
    hb = FakeHeartbeatManager()
    bridge.register_v2_supervisor("r1", FakeSupervisor(), hb, "plugin_runtime_v2")

    await bridge._on_v2_timeout("r1", {"consecutive_failures": 3})

    assert len(received) == 1
    event = received[0]
    assert event.component_id == "plugin_runtime_v2"
    assert event.reason.value == "runner_unresponsive"
    assert "source=heartbeat" in event.detail
    assert "consecutive_failures=3" in event.detail
    assert "runner_id=r1" in event.detail


@pytest.mark.asyncio
async def test_cooldown_prevents_duplicate_report(monkeypatch: pytest.MonkeyPatch):
    """AC-1.3.2: 冷却窗口内再次心跳超时不重复上报。"""
    monkeypatch.setattr(
        "src.core.watchdog.runner_health_bridge.get_service_manager_port",
        lambda: FakeServiceManager(),
    )
    bridge, received = _make_bridge()
    hb = FakeHeartbeatManager()
    bridge.register_v2_supervisor("r1", FakeSupervisor(), hb, "plugin_runtime_v2")

    await bridge._on_v2_timeout("r1", {"consecutive_failures": 2})
    assert len(received) == 1

    # 冷却窗口内（cooldown_s=30）再次触发
    await bridge._on_v2_timeout("r1", {"consecutive_failures": 2})
    assert len(received) == 1


@pytest.mark.asyncio
async def test_register_v2_supervisor_idempotent():
    """数据约束 3: 重复 register_v2_supervisor 幂等（状态表唯一、poll Task 唯一、监听器注入一次）。"""
    bridge, _ = _make_bridge()
    hb = FakeHeartbeatManager()
    sv = FakeSupervisor()

    bridge.register_v2_supervisor("r1", sv, hb, "plugin_runtime_v2")
    bridge.register_v2_supervisor("r1", sv, hb, "plugin_runtime_v2")  # 重复

    assert len(bridge._bridge_status) == 1
    assert len(bridge._v2_supervisors) == 1
    assert len(bridge._poll_tasks) == 1
    assert len(hb.added) == 1


@pytest.mark.asyncio
async def test_register_v1_supervisor_idempotent():
    """数据约束 3: 重复 register_v1_supervisor 幂等。"""

    class FakeV1:
        def __init__(self) -> None:
            self._runner_process = None
            self._restart_count = 0

    bridge, _ = _make_bridge()
    sv = FakeV1()

    bridge.register_v1_supervisor("v1-builtin", sv, "plugin_runtime")
    bridge.register_v1_supervisor("v1-builtin", sv, "plugin_runtime")  # 重复

    assert len(bridge._bridge_status) == 1
    assert len(bridge._v1_supervisors) == 1
    assert len(bridge._poll_tasks) == 1


@pytest.mark.asyncio
async def test_unregister_removes_timeout_listener():
    """注销 V2 条目时心跳监听器被摘除。"""
    bridge, _ = _make_bridge()
    hb = FakeHeartbeatManager()
    bridge.register_v2_supervisor("r1", FakeSupervisor(), hb, "plugin_runtime_v2")

    bridge.unregister_runner("r1")

    assert len(hb.removed) == 1
    removed_rid, removed_listener = hb.removed[0]
    assert removed_rid == "r1"
    assert removed_listener == bridge._on_v2_timeout
    assert "r1" not in bridge._bridge_status
    assert "r1" not in bridge._poll_tasks


@pytest.mark.asyncio
async def test_register_v2_injects_timeout_listener():
    """FR-1 根因: register_v2_supervisor 注入 _on_v2_timeout 监听器到 heartbeat_manager。"""
    bridge, _ = _make_bridge()
    hb = FakeHeartbeatManager()

    bridge.register_v2_supervisor("r1", FakeSupervisor(), hb, "plugin_runtime_v2")

    assert len(hb.added) == 1
    added_rid, added_listener = hb.added[0]
    assert added_rid == "r1"
    assert added_listener == bridge._on_v2_timeout
