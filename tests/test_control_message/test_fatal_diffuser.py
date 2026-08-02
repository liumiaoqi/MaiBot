"""T10 FatalDiffuser 单元测试 — 致命扩散引擎。"""

import asyncio

import pytest

from src.core.control_message.fatal_diffuser import FatalDiffuser
from src.core.control_message.types import (
    ControlMessageKind,
)


class _MockLifecycle:
    def __init__(self, tasks: list) -> None:
        self._tasks = tasks
        self.query_fail = False

    async def list_session_async_tasks(self, session_id: str) -> list:
        if self.query_fail:
            raise RuntimeError("lifecycle unavailable")
        return self._tasks


class _FakeEventBus:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    async def emit(self, event_type: str, data: dict) -> None:
        self.events.append((event_type, data))


async def _make_cooperative_task() -> asyncio.Task:
    """一个可被取消的协程任务（取消时抛 CancelledError）。"""

    async def sleeper() -> None:
        while True:
            await asyncio.sleep(3600)

    return asyncio.create_task(sleeper())


class TestFatalIdentification:
    @pytest.mark.asyncio
    async def test_fatal_kind_identified(self) -> None:
        """SESSION_DESTROY 识别为致命，触发扩散（spec §5.9.1 规则 1）。"""
        lifecycle = _MockLifecycle([])
        diffuser = FatalDiffuser(session_lifecycle_port=lifecycle)
        record = await diffuser.diffuse("s1", ControlMessageKind.SESSION_DESTROY)
        assert record is not None
        assert record.total_tasks == 0

    @pytest.mark.asyncio
    async def test_non_fatal_no_diffuse(self) -> None:
        """非致命不扩散（spec §5.9.1 规则 1）。"""
        lifecycle = _MockLifecycle([])
        diffuser = FatalDiffuser(session_lifecycle_port=lifecycle)
        assert await diffuser.diffuse("s1", ControlMessageKind.PAUSE_REPLY) is None
        assert await diffuser.diffuse("s1", ControlMessageKind.EMERGENCY_STOP) is None


class TestDiffuse:
    @pytest.mark.asyncio
    async def test_diffuse_all_tasks(self) -> None:
        """扩散覆盖全部关联任务，不遗漏（spec §4.2 可靠性 4）。"""
        tasks = [await _make_cooperative_task() for _ in range(3)]
        lifecycle = _MockLifecycle(tasks)
        diffuser = FatalDiffuser(session_lifecycle_port=lifecycle)
        await diffuser.diffuse("s1", ControlMessageKind.SESSION_DESTROY)
        # 等待后台 worker 完成
        for _ in range(100):
            if diffuser.get_diffuse_history():
                break
            await asyncio.sleep(0.01)
        records = diffuser.get_diffuse_history()
        assert len(records) == 1
        assert records[0].total_tasks == 3
        assert records[0].cancelled_tasks == 3
        assert records[0].failed_tasks == 0
        for t in tasks:
            assert t.cancelled()

    @pytest.mark.asyncio
    async def test_diffuse_async_not_blocking(self) -> None:
        """扩散异步不阻塞控制消息处理（spec §5.9.1 规则 4）。"""
        tasks = [await _make_cooperative_task() for _ in range(5)]
        lifecycle = _MockLifecycle(tasks)
        diffuser = FatalDiffuser(session_lifecycle_port=lifecycle)
        # diffuse 返回时扩散尚未完成（异步），不等待
        result = await diffuser.diffuse("s1", ControlMessageKind.SESSION_DESTROY)
        assert result is None  # 有关联任务时结果由后台 worker 记录
        # 任务已被取消（后台进行中）
        await asyncio.sleep(0.1)
        for t in tasks:
            assert t.cancelled()

    @pytest.mark.asyncio
    async def test_diffuse_result_recorded(self) -> None:
        """扩散结果记录 total/cancelled/failed（spec §5.9.1 规则 5）。"""
        good = await _make_cooperative_task()

        async def stubborn() -> None:
            try:
                while True:
                    await asyncio.sleep(3600)
            except asyncio.CancelledError:
                raise RuntimeError("refusing cancel")

        stubborn_task = asyncio.create_task(stubborn())
        lifecycle = _MockLifecycle([good, stubborn_task])
        diffuser = FatalDiffuser(session_lifecycle_port=lifecycle)
        await diffuser.diffuse("s1", ControlMessageKind.SESSION_DESTROY)
        for _ in range(100):
            if diffuser.get_diffuse_history():
                break
            await asyncio.sleep(0.01)
        records = diffuser.get_diffuse_history()
        assert records[0].total_tasks == 2
        assert records[0].cancelled_tasks == 1
        assert records[0].failed_tasks == 1

    @pytest.mark.asyncio
    async def test_diffuse_query_failed_skips(self) -> None:
        """查询失败跳过扩散（spec §5.9.2 异常场景 1）。"""
        lifecycle = _MockLifecycle([])
        lifecycle.query_fail = True
        diffuser = FatalDiffuser(session_lifecycle_port=lifecycle)
        assert await diffuser.diffuse("s1", ControlMessageKind.SESSION_DESTROY) is None
        assert diffuser.get_diffuse_history() == []

    @pytest.mark.asyncio
    async def test_zap_completed_event(self) -> None:
        """发布 control.zap_completed 事件。"""
        tasks = [await _make_cooperative_task() for _ in range(2)]
        lifecycle = _MockLifecycle(tasks)
        bus = _FakeEventBus()
        diffuser = FatalDiffuser(session_lifecycle_port=lifecycle, event_bus=bus)
        await diffuser.diffuse("s1", ControlMessageKind.SESSION_DESTROY)
        for _ in range(100):
            if bus.events:
                break
            await asyncio.sleep(0.01)
        assert any(t == "control.zap_completed" for t, _ in bus.events)
        event = next(d for t, d in bus.events if t == "control.zap_completed")
        assert event["total"] == 2
        assert event["cancelled"] == 2

    @pytest.mark.asyncio
    async def test_diffuse_history_ring_buffer(self) -> None:
        """扩散历史环形缓冲上限 100。"""
        diffuser = FatalDiffuser(session_lifecycle_port=_MockLifecycle([]))
        for i in range(120):
            await diffuser.diffuse(f"s{i}", ControlMessageKind.SESSION_DESTROY)
        assert len(diffuser.get_diffuse_history()) == 100

    @pytest.mark.asyncio
    async def test_no_lifecycle_port_skips(self) -> None:
        """无生命周期端口（未注入）跳过扩散。"""
        diffuser = FatalDiffuser(session_lifecycle_port=None)
        assert await diffuser.diffuse("s1", ControlMessageKind.SESSION_DESTROY) is None
