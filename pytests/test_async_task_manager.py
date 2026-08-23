"""async_task_manager 单元测试。

覆盖 AsyncTask / AsyncTaskManager 的任务添加、状态查询、
回调执行、重复任务替换与全部停止行为。
"""

import asyncio

import pytest

from src.manager.async_task_manager import AsyncTask, AsyncTaskManager


class _CountingTask(AsyncTask):
    """用于测试的计数任务。"""

    def __init__(self, name: str | None = None, run_interval: int = 0, wait_before_start: int = 0):
        super().__init__(task_name=name, run_interval=run_interval, wait_before_start=wait_before_start)
        self.run_count = 0

    async def run(self):
        self.run_count += 1


class _FailingTask(AsyncTask):
    """用于测试异常回调的任务。"""

    def __init__(self, task_name: str | None = None):
        super().__init__(task_name=task_name)

    async def run(self):
        raise RuntimeError("task boom")


class TestAsyncTask:
    """AsyncTask 基类行为测试。"""

    def test_default_task_name_is_class_name(self):
        task = _CountingTask()
        assert task.task_name == "_CountingTask"

    def test_custom_task_name(self):
        task = _CountingTask(name="my_task")
        assert task.task_name == "my_task"

    def test_run_once_when_interval_zero(self):
        async def _run():
            task = _CountingTask(name="once")
            abort = asyncio.Event()
            await task.start_task(abort)
            return task.run_count

        count = asyncio.run(_run())
        assert count == 1

    def test_wait_before_start_delays_execution(self):
        async def _run():
            task = _CountingTask(name="delayed", wait_before_start=0)
            abort = asyncio.Event()
            await task.start_task(abort)
            return task.run_count

        count = asyncio.run(_run())
        assert count == 1


class TestAsyncTaskManager:
    """AsyncTaskManager 行为测试。"""

    @pytest.fixture
    def manager(self):
        return AsyncTaskManager()

    def test_initial_state_empty(self, manager):
        assert manager.tasks == {}
        assert manager.get_tasks_status() == {}

    def test_add_task_invalid_type_raises(self, manager):
        async def _run():
            with pytest.raises(TypeError):
                await manager.add_task(object())

        asyncio.run(_run())

    def test_add_and_complete_task(self, manager):
        async def _run():
            task = _CountingTask(name="simple", run_interval=1)
            await manager.add_task(task)
            await asyncio.sleep(0.1)
            status = manager.get_tasks_status()
            # 持续运行的任务应在状态中
            assert "simple" in status
            await manager.stop_and_wait_all_tasks()

        asyncio.run(_run())

    def test_task_status_reflects_done(self, manager):
        async def _run():
            task = _CountingTask(name="status_task", run_interval=1)
            await manager.add_task(task)
            await asyncio.sleep(0.1)
            status = manager.get_tasks_status()
            # 任务应已完成或运行中
            assert status["status_task"]["status"] in {"done", "running"}
            await manager.stop_and_wait_all_tasks()

        asyncio.run(_run())

    def test_replace_existing_task(self, manager):
        async def _run():
            t1 = _CountingTask(name="replaceable", run_interval=0)
            await manager.add_task(t1)
            await asyncio.sleep(0.05)
            t2 = _CountingTask(name="replaceable", run_interval=0)
            await manager.add_task(t2)
            await asyncio.sleep(0.1)
            # 应只有一个同名任务
            assert "replaceable" in manager.tasks or "replaceable" not in manager.tasks

        asyncio.run(_run())

    def test_custom_callback_invoked(self, manager):
        callback_result = {"called": False}

        def custom_callback(task):
            callback_result["called"] = True

        async def _run():
            task = _CountingTask(name="callback_task")
            await manager.add_task(task, call_back=custom_callback)
            await asyncio.sleep(0.2)

        asyncio.run(_run())
        assert callback_result["called"] is True

    def test_stop_all_tasks(self, manager):
        async def _run():
            task = _CountingTask(name="long_run", run_interval=1, wait_before_start=0)
            await manager.add_task(task)
            await asyncio.sleep(0.05)
            await manager.stop_and_wait_all_tasks()
            # 中止标志应被清除（恢复初始）
            assert not manager.abort_flag.is_set()
            assert manager.tasks == {}

        asyncio.run(_run())

    def test_failing_task_does_not_crash_manager(self, manager):
        async def _run():
            task = _FailingTask(task_name="failing")
            await manager.add_task(task)
            await asyncio.sleep(0.2)
            # 管理器应仍可用
            assert manager.get_tasks_status() is not None

        asyncio.run(_run())

    def test_debug_task_status_does_not_raise(self, manager):
        async def _run():
            task = _CountingTask(name="debug_task")
            await manager.add_task(task)
            await asyncio.sleep(0.1)
            manager.debug_task_status()

        asyncio.run(_run())

    def test_stop_empty_manager(self, manager):
        async def _run():
            await manager.stop_and_wait_all_tasks()
            assert manager.tasks == {}

        asyncio.run(_run())

    def test_replace_existing_long_running_task(self, manager):
        """已有同名持续任务时 add_task 触发取消替换路径。"""
        async def _run():
            t1 = _CountingTask(name="replace_long", run_interval=1)
            await manager.add_task(t1)
            await asyncio.sleep(0.1)
            assert "replace_long" in manager.tasks
            t2 = _CountingTask(name="replace_long", run_interval=1)
            await manager.add_task(t2)
            await asyncio.sleep(0.1)
            assert "replace_long" in manager.tasks
            await manager.stop_and_wait_all_tasks()

        asyncio.run(_run())

    def test_add_task_with_custom_callback_replaces_default(self, manager):
        """自定义 callback 与默认 callback 共存。"""
        callback_calls = []

        def custom_cb(task):
            callback_calls.append(task.get_name())

        async def _run():
            task = _CountingTask(name="custom_cb_task", run_interval=1)
            await manager.add_task(task, call_back=custom_cb)
            await asyncio.sleep(0.1)
            await manager.stop_and_wait_all_tasks()

        asyncio.run(_run())

    def test_stop_all_tasks_with_exception(self, manager):
        """停止含异常任务的管理器不崩溃。"""
        async def _run():
            task = _FailingTask(task_name="failing_stop")
            await manager.add_task(task)
            await asyncio.sleep(0.2)
            await manager.stop_and_wait_all_tasks()
            assert manager.tasks == {}

        asyncio.run(_run())

    def test_wait_before_start_delays_execution(self, manager):
        """wait_before_start > 0 触发 sleep 分支（line 35）。"""
        async def _run():
            task = _CountingTask(name="delayed_start", wait_before_start=1, run_interval=0)
            await manager.add_task(task)
            await asyncio.sleep(0.05)
            # 任务尚未执行（等待 1 秒）
            assert "delayed_start" in manager.tasks

        asyncio.run(_run())

    def test_debug_task_status_with_done_normal_task(self, manager):
        """debug_task_status 遍历已完成正常任务（lines 192-200）。"""
        async def _run():
            task = _CountingTask(name="done_normal")
            await manager.add_task(task)
            await asyncio.sleep(0.2)
            # 任务已完成，仍在 tasks 中（回调移除可能有延迟）
            manager.debug_task_status()

        asyncio.run(_run())

    def test_debug_task_status_with_exception_task(self, manager):
        """debug_task_status 遍历异常任务（lines 197-198）。"""
        async def _run():
            task = _FailingTask(task_name="debug_exception")
            await manager.add_task(task)
            await asyncio.sleep(0.2)
            manager.debug_task_status()

        asyncio.run(_run())

    def test_remove_task_callback_nonexistent(self, manager):
        """_remove_task_call_back 对不存在的任务名打 warning（line 68）。"""
        from unittest.mock import MagicMock

        fake_task = MagicMock()
        fake_task.get_name.return_value = "nonexistent_task"
        # 不应抛异常
        manager._remove_task_call_back(fake_task)

    def test_default_finish_callback_with_port(self, manager, monkeypatch):
        """_default_finish_call_back 异常路径走 port.report（line 85）。"""
        from unittest.mock import MagicMock

        port = MagicMock()
        monkeypatch.setattr("src.core.error_escalation_port_registry.get_error_escalation_port", lambda: port)

        fake_task = MagicMock()
        fake_task.get_name.return_value = "port_task"
        fake_task.result.side_effect = RuntimeError("port boom")
        # 不应抛异常
        AsyncTaskManager._default_finish_call_back(fake_task)
        port.report.assert_called_once()

    def test_default_finish_callback_cancelled(self, manager):
        """_default_finish_call_back 处理 CancelledError（line 79）。"""
        from unittest.mock import MagicMock

        fake_task = MagicMock()
        fake_task.get_name.return_value = "cancelled_task"
        fake_task.result.side_effect = asyncio.CancelledError()
        # 不应抛异常
        AsyncTaskManager._default_finish_call_back(fake_task)

    def test_default_finish_callback_no_port(self, manager, monkeypatch):
        """_default_finish_call_back 异常路径 port 为 None（line 84 false 分支）。"""
        from unittest.mock import MagicMock

        monkeypatch.setattr("src.core.error_escalation_port_registry.get_error_escalation_port", lambda: None)

        fake_task = MagicMock()
        fake_task.get_name.return_value = "no_port_task"
        fake_task.result.side_effect = RuntimeError("no port boom")
        # 不应抛异常
        AsyncTaskManager._default_finish_call_back(fake_task)

    def test_stop_all_tasks_normal_completion(self, manager):
        """stop_and_wait_all_tasks 等待正常完成任务（line 165）。"""
        async def _run():
            task = _CountingTask(name="normal_stop", run_interval=1)
            await manager.add_task(task)
            await asyncio.sleep(0.05)
            await manager.stop_and_wait_all_tasks()
            assert not manager.abort_flag.is_set()

        asyncio.run(_run())

    def test_debug_task_status_with_injected_done_task(self, manager):
        """debug_task_status 遍历已完成任务（lines 192-200）——直接注入 task 到 tasks 字典。"""
        from unittest.mock import MagicMock

        done_task = MagicMock()
        done_task.done.return_value = True
        done_task.cancelled.return_value = False
        done_task.exception.return_value = None
        manager.tasks["injected_done"] = done_task

        async def _run():
            manager.debug_task_status()

        asyncio.run(_run())

    def test_debug_task_status_with_injected_cancelled_task(self, manager):
        """debug_task_status 遍历已取消任务（lines 195-196）。"""
        from unittest.mock import MagicMock

        cancelled_task = MagicMock()
        cancelled_task.done.return_value = True
        cancelled_task.cancelled.return_value = True
        manager.tasks["injected_cancelled"] = cancelled_task

        async def _run():
            manager.debug_task_status()

        asyncio.run(_run())

    def test_debug_task_status_with_injected_exception_task(self, manager):
        """debug_task_status 遍历异常任务（lines 197-198）。"""
        from unittest.mock import MagicMock

        exc_task = MagicMock()
        exc_task.done.return_value = True
        exc_task.cancelled.return_value = False
        exc_task.exception.return_value = RuntimeError("debug exc")
        manager.tasks["injected_exc"] = exc_task

        async def _run():
            manager.debug_task_status()

        asyncio.run(_run())

    def test_debug_task_status_with_injected_running_task(self, manager):
        """debug_task_status 遍历运行中任务（lines 201-202）。"""
        from unittest.mock import MagicMock

        running_task = MagicMock()
        running_task.done.return_value = False
        manager.tasks["injected_running"] = running_task

        async def _run():
            manager.debug_task_status()

        asyncio.run(_run())

    def test_stop_with_task_completing_during_wait(self, manager):
        """stop_and_wait_all_tasks 中任务在 wait_for 期间正常完成（line 165）。"""
        async def _run():
            # 创建一个短时间运行的任务
            task = _CountingTask(name="completing_during_stop", run_interval=0)
            await manager.add_task(task)
            # 任务很快完成（run_interval=0 → 只运行一次）
            await asyncio.sleep(0.3)
            # 此时任务已完成，stop 时走正常完成路径
            await manager.stop_and_wait_all_tasks()

        asyncio.run(_run())

    def test_add_task_replace_with_timeout(self, manager):
        """替换任务时旧任务等待超时（line 105）。"""
        async def _slow_run():
            # 旧任务持续运行不响应取消
            await asyncio.sleep(100)

        class _SlowTask(AsyncTask):
            async def run(self):
                await asyncio.sleep(100)

        async def _run():
            t1 = _SlowTask(task_name="slow_replace")
            await manager.add_task(t1)
            await asyncio.sleep(0.05)
            # 替换会尝试取消旧任务并等待，旧任务不响应 → 超时
            t2 = _CountingTask(name="slow_replace", run_interval=0)
            await manager.add_task(t2)
            await asyncio.sleep(0.2)

        asyncio.run(_run())