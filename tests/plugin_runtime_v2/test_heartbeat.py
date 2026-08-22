"""HeartbeatManager 单元测试 — 心跳保活 + P1-14 stop cancel 无 await。

覆盖：
- 构造与默认状态
- start/stop/stop_all 生命周期
- record_response 重置丢失计数
- add/remove_timeout_listener 旁路监听器
- _heartbeat_loop 超时判定 + 旁路监听器优先执行
- P1-14: stop 是同步方法，cancel 后不 await task（防关闭路径阻塞）
"""

import asyncio
import inspect
from unittest.mock import AsyncMock

import pytest

from src.plugin_runtime_v2.host.heartbeat import HeartbeatManager


class TestHeartbeatConstruct:
    """构造与默认状态。"""

    def test_init_stores_params(self):
        mgr = HeartbeatManager(interval_s=30, timeout_s=10, max_misses=2)
        assert mgr._interval_s == 30
        assert mgr._timeout_s == 10
        assert mgr._max_misses == 2

    def test_init_empty_state(self):
        mgr = HeartbeatManager(interval_s=30, timeout_s=10, max_misses=2)
        assert mgr._tasks == {}
        assert mgr._response_events == {}
        assert mgr._miss_counts == {}
        assert mgr._timeout_listeners == {}


class TestHeartbeatStartStop:
    """start/stop 生命周期 + P1-14 stop cancel 无 await。"""

    @pytest.mark.asyncio
    async def test_start_creates_task(self):
        mgr = HeartbeatManager(interval_s=30, timeout_s=10, max_misses=2)
        mgr.start("r1", AsyncMock(), AsyncMock())
        assert "r1" in mgr._tasks
        assert isinstance(mgr._tasks["r1"], asyncio.Task)
        assert "r1" in mgr._response_events
        assert mgr._miss_counts["r1"] == 0
        mgr.stop("r1")
        await self._drain_task(mgr, "r1")

    @pytest.mark.asyncio
    async def test_start_duplicate_ignored(self):
        """同一 runner_id 重复 start 不创建新任务。"""
        mgr = HeartbeatManager(interval_s=30, timeout_s=10, max_misses=2)
        mgr.start("r1", AsyncMock(), AsyncMock())
        first_task = mgr._tasks["r1"]
        mgr.start("r1", AsyncMock(), AsyncMock())
        assert mgr._tasks["r1"] is first_task
        mgr.stop("r1")
        await self._drain_task(mgr, "r1")

    def test_stop_is_sync_no_await(self):
        """P1-14: stop 是同步方法，只 cancel 不 await task。"""
        mgr = HeartbeatManager(interval_s=30, timeout_s=10, max_misses=2)
        # stop 不应是协程函数——同步调用避免关闭路径阻塞
        assert not inspect.iscoroutinefunction(mgr.stop)

    @pytest.mark.asyncio
    async def test_stop_cancels_task_without_await(self):
        """P1-14: stop cancel 后无 await——task 被 cancel 但 stop 不等待其完成。"""
        mgr = HeartbeatManager(interval_s=30, timeout_s=10, max_misses=2)
        mgr.start("r1", AsyncMock(), AsyncMock())
        task = mgr._tasks["r1"]
        assert not task.cancelled()
        mgr.stop("r1")  # 同步调用，不 await
        # task 被 cancel（cancelling 状态，因 stop 未 await 故未必已 cancelled）
        assert task.cancelling() >= 1 or task.cancelled()
        assert "r1" not in mgr._tasks
        assert "r1" not in mgr._response_events
        assert "r1" not in mgr._miss_counts
        await self._drain_task(mgr, "r1", task=task)

    @pytest.mark.asyncio
    async def test_stop_unknown_runner_silent(self):
        """stop 不存在的 runner 静默忽略。"""
        mgr = HeartbeatManager(interval_s=30, timeout_s=10, max_misses=2)
        mgr.stop("nonexistent")  # 不抛异常

    @pytest.mark.asyncio
    async def test_stop_all(self):
        mgr = HeartbeatManager(interval_s=30, timeout_s=10, max_misses=2)
        mgr.start("r1", AsyncMock(), AsyncMock())
        mgr.start("r2", AsyncMock(), AsyncMock())
        tasks = list(mgr._tasks.values())
        mgr.stop_all()
        assert mgr._tasks == {}
        for t in tasks:
            try:
                await t
            except asyncio.CancelledError:
                pass

    @staticmethod
    async def _drain_task(mgr: HeartbeatManager, runner_id: str, task=None) -> None:
        """清理已 cancel 的 task 避免 pytest 警告。"""
        t = task or mgr._tasks.get(runner_id)
        if t is None:
            return
        try:
            await t
        except (asyncio.CancelledError, Exception):
            pass


class TestHeartbeatRecordResponse:
    """record_response 重置丢失计数。"""

    @pytest.mark.asyncio
    async def test_record_response_resets_miss(self):
        mgr = HeartbeatManager(interval_s=30, timeout_s=10, max_misses=2)
        mgr.start("r1", AsyncMock(), AsyncMock())
        mgr._miss_counts["r1"] = 5
        mgr.record_response("r1")
        assert mgr._miss_counts["r1"] == 0
        # event 被 set
        assert mgr._response_events["r1"].is_set()
        mgr.stop("r1")
        await TestHeartbeatStartStop._drain_task(mgr, "r1")

    def test_record_response_unknown_runner_silent(self):
        mgr = HeartbeatManager(interval_s=30, timeout_s=10, max_misses=2)
        mgr.record_response("nonexistent")  # 不抛异常


class TestHeartbeatTimeoutListener:
    """add/remove_timeout_listener。"""

    def test_add_timeout_listener(self):
        mgr = HeartbeatManager(interval_s=30, timeout_s=10, max_misses=2)
        listener = AsyncMock()
        mgr.add_timeout_listener("r1", listener)
        assert listener in mgr._timeout_listeners["r1"]

    def test_add_timeout_listener_dedup(self):
        """同一 listener 重复注册不重复（set 去重）。"""
        mgr = HeartbeatManager(interval_s=30, timeout_s=10, max_misses=2)
        listener = AsyncMock()
        mgr.add_timeout_listener("r1", listener)
        mgr.add_timeout_listener("r1", listener)
        assert len(mgr._timeout_listeners["r1"]) == 1

    def test_remove_timeout_listener(self):
        mgr = HeartbeatManager(interval_s=30, timeout_s=10, max_misses=2)
        listener = AsyncMock()
        mgr.add_timeout_listener("r1", listener)
        mgr.remove_timeout_listener("r1", listener)
        assert "r1" not in mgr._timeout_listeners

    def test_remove_timeout_listener_unknown_silent(self):
        mgr = HeartbeatManager(interval_s=30, timeout_s=10, max_misses=2)
        mgr.remove_timeout_listener("nonexistent", AsyncMock())  # 不抛异常

    @pytest.mark.asyncio
    async def test_stop_clears_listeners(self):
        mgr = HeartbeatManager(interval_s=30, timeout_s=10, max_misses=2)
        mgr.start("r1", AsyncMock(), AsyncMock())
        mgr.add_timeout_listener("r1", AsyncMock())
        mgr.stop("r1")
        assert "r1" not in mgr._timeout_listeners
        await TestHeartbeatStartStop._drain_task(mgr, "r1")


class TestHeartbeatLoopTimeout:
    """_heartbeat_loop 超时判定 + 旁路监听器优先执行。"""

    @pytest.mark.asyncio
    async def test_timeout_callback_invoked_on_max_misses(self):
        """连续超时达 max_misses 后调用 timeout_callback。"""
        mgr = HeartbeatManager(interval_s=0.05, timeout_s=0.05, max_misses=1)
        send_cb = AsyncMock()  # 不设置 event → 响应超时
        timeout_cb = AsyncMock()
        mgr.start("r1", send_cb, timeout_cb)
        # 等待超时触发（interval + timeout + 余量）
        await asyncio.sleep(0.2)
        timeout_cb.assert_awaited()
        mgr.stop("r1")

    @pytest.mark.asyncio
    async def test_timeout_callback_two_arg_signature(self):
        """新签名 timeout_callback(runner_id, context) 被正确调用。"""
        mgr = HeartbeatManager(interval_s=0.05, timeout_s=0.05, max_misses=1)
        send_cb = AsyncMock()
        calls: list = []

        async def timeout_cb(rid, ctx=None):
            calls.append((rid, ctx))

        mgr.start("r1", send_cb, timeout_cb)
        await asyncio.sleep(0.2)
        assert len(calls) >= 1
        assert calls[0][0] == "r1"
        assert calls[0][1]["detection_source"] == "heartbeat"
        assert calls[0][1]["consecutive_failures"] == 1
        mgr.stop("r1")

    @pytest.mark.asyncio
    async def test_bypass_listener_invoked_before_callback(self):
        """旁路监听器在 timeout_callback 之前被调用。"""
        mgr = HeartbeatManager(interval_s=0.05, timeout_s=0.05, max_misses=1)
        send_cb = AsyncMock()
        order: list = []

        async def listener(rid, ctx):
            order.append("listener")

        async def timeout_cb(rid, ctx=None):
            order.append("callback")

        mgr.add_timeout_listener("r1", listener)
        mgr.start("r1", send_cb, timeout_cb)
        await asyncio.sleep(0.2)
        assert "listener" in order
        assert "callback" in order
        assert order.index("listener") < order.index("callback")
        mgr.stop("r1")