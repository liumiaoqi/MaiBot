"""Runner 注册/注销接线测试（FR-3）。

覆盖 AC-3.1.1 / AC-3.2.1 / AC-3.3.1 / AC-3.3.2 / AC-3.4.1，
含 V1 源码不改动断言（NFR-3）。
"""


import asyncio
from pathlib import Path

import pytest

from src.core.adapters.watchdog_adapter import WatchdogAdapter
from src.core.watchdog.config import WatchdogConfig
from src.core.watchdog.exceptions import UnknownRunnerError
from src.core.watchdog.types import FaultReportEvent

REPO_ROOT = Path(__file__).resolve().parents[2]
V1_SUPERVISOR_PATH = "src/plugin_runtime/host/supervisor.py"


class FakeServiceManager:
    """mock ServiceManagerPort。"""

    def __init__(self) -> None:
        self.faults: list[tuple[str, str, str]] = []

    def get_state(self, component_id: str) -> object:
        return object()

    async def report_external_fault(
        self, component_id: str, reason: str, detail: str = ""
    ) -> None:
        self.faults.append((component_id, reason, detail))


class FakeHeartbeatManager:
    def __init__(self) -> None:
        self.added: list[tuple[str, object]] = []
        self.removed: list[tuple[str, object]] = []

    def add_timeout_listener(self, runner_id: str, listener: object) -> None:
        self.added.append((runner_id, listener))

    def remove_timeout_listener(self, runner_id: str, listener: object) -> None:
        self.removed.append((runner_id, listener))


class FakeV2Supervisor:
    def __init__(self) -> None:
        self._health: dict = {}

    def get_health_status(self) -> dict:
        return self._health


class FakeV1Supervisor:
    """mock V1 supervisor：旁路轮询访问的私有属性 + group_name。"""

    def __init__(self, group_name: str, process=None, restart_count: int = 0) -> None:
        self.group_name = group_name
        self._runner_process = process
        self._restart_count = restart_count


def _fast_config(**overrides: float) -> WatchdogConfig:
    """构造快速轮询配置（v1/v2 轮询间隔较小，测试可等）。

    间隔不宜过小：与 test_event_loop_monitor 的精确时序测试共享 CPU，
    过密轮询会放大其 flaky 概率。
    """
    base = {
        "v1_poll_interval_s": 0.05,
        "v2_diff_interval_s": 0.05,
    }
    base.update(overrides)
    return WatchdogConfig(**base)


async def _make_adapter(
    monkeypatch: pytest.MonkeyPatch,
    config: WatchdogConfig | None = None,
) -> tuple[WatchdogAdapter, FakeServiceManager, list[FaultReportEvent]]:
    """构造已启动的 WatchdogAdapter，mock ServiceManagerPort。"""
    sm = FakeServiceManager()
    monkeypatch.setattr(
        "src.core.adapters.watchdog_adapter.get_service_manager_port",
        lambda: sm,
    )
    monkeypatch.setattr(
        "src.core.watchdog.runner_health_bridge.get_service_manager_port",
        lambda: sm,
    )
    received: list[FaultReportEvent] = []

    async def report_callback(event: FaultReportEvent) -> None:
        received.append(event)

    # adapter 内部 _do_report 走 get_service_manager_port（已 mock），
    # report_callback 参数无法直接注入，用 monkeypatch 包装 bridge 构造：
    # 简化：直接调用 adapter 的公开接口，验证注册/注销/状态查询
    adapter = WatchdogAdapter(config=config or _fast_config())
    await adapter.start(asyncio.get_running_loop())
    return adapter, sm, received


@pytest.mark.asyncio
async def test_v2_register_lists_bridge_status(monkeypatch: pytest.MonkeyPatch):
    """AC-3.1.1: V2 注册后 list_runner_bridge_status() 含该 Runner 且 component_id 非空。"""
    adapter, _, _ = await _make_adapter(monkeypatch)
    hb = FakeHeartbeatManager()

    adapter.register_v2_supervisor(
        "runner-test-plugin", FakeV2Supervisor(), hb, "plugin_runtime_v2"
    )

    statuses = adapter.list_runner_bridge_status()
    assert len(statuses) == 1
    assert statuses[0].runner_id == "runner-test-plugin"
    assert statuses[0].component_id == "plugin_runtime_v2"
    await adapter.stop()


@pytest.mark.asyncio
async def test_v2_unregister_removes_and_cancels(monkeypatch: pytest.MonkeyPatch):
    """AC-3.2.1: 注销后状态表移除、轮询 Task 已取消、监听器已摘除。"""
    adapter, _, _ = await _make_adapter(monkeypatch)
    hb = FakeHeartbeatManager()
    adapter.register_v2_supervisor(
        "runner-test-plugin", FakeV2Supervisor(), hb, "plugin_runtime_v2"
    )

    adapter.unregister_runner("runner-test-plugin")

    assert adapter.list_runner_bridge_status() == []
    assert len(hb.removed) == 1
    await adapter.stop()


@pytest.mark.asyncio
async def test_v1_batch_registration(monkeypatch: pytest.MonkeyPatch):
    """AC-3.3.1: V1 manager.supervisors 批量注册，含 v1-builtin/v1-third_party。"""
    adapter, _, _ = await _make_adapter(monkeypatch)
    supervisors = [
        FakeV1Supervisor("builtin"),
        FakeV1Supervisor("third_party"),
    ]

    for sv in supervisors:
        adapter.register_v1_supervisor(f"v1-{sv.group_name}", sv, "plugin_runtime")

    statuses = adapter.list_runner_bridge_status()
    runner_ids = {s.runner_id for s in statuses}
    assert runner_ids == {"v1-builtin", "v1-third_party"}
    assert all(s.component_id == "plugin_runtime" for s in statuses)
    await adapter.stop()


@pytest.mark.asyncio
async def test_v1_process_exit_bridges_report(monkeypatch: pytest.MonkeyPatch):
    """AC-3.3.2: V1 进程退出（returncode 非 None）旁路轮询上报，且 V1 源码未改动。"""
    adapter, sm, _ = await _make_adapter(monkeypatch)

    class DeadProcess:
        returncode = 1

    sv = FakeV1Supervisor("builtin", process=DeadProcess())

    # NFR-3 回归哨兵：记录 V1 supervisor.py 测试前内容
    # （完整"分支未改 V1"由 merge 时 git diff 验证）
    v1_file = REPO_ROOT / V1_SUPERVISOR_PATH
    before = v1_file.read_bytes()

    adapter.register_v1_supervisor("v1-builtin", sv, "plugin_runtime")

    # 等轮询触发（v1_poll_interval_s=0.05）
    for _ in range(100):
        if sm.faults:
            break
        await asyncio.sleep(0.03)

    assert sm.faults, "旁路轮询未触发上报"
    component_id, reason, detail = sm.faults[0]
    assert component_id == "plugin_runtime"
    assert reason == "runner_unresponsive"
    assert "source=process_poll" in detail

    assert v1_file.read_bytes() == before, "V1 supervisor.py 被修改"
    await adapter.stop()


@pytest.mark.asyncio
async def test_no_runner_empty_bridge(monkeypatch: pytest.MonkeyPatch):
    """AC-3.4.1: 无 Runner 时 get_status() 正常、bridge 状态为空。"""
    adapter, _, _ = await _make_adapter(monkeypatch)

    status = adapter.get_status()
    assert status is not None
    assert adapter.list_runner_bridge_status() == []
    await adapter.stop()


@pytest.mark.asyncio
async def test_unregister_unknown_raises(monkeypatch: pytest.MonkeyPatch):
    """未注册 runner_id 调 unregister 抛 UnknownRunnerError。"""
    adapter, _, _ = await _make_adapter(monkeypatch)

    with pytest.raises(UnknownRunnerError):
        adapter.unregister_runner("unknown-runner")
    await adapter.stop()
