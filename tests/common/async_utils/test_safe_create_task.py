"""_safe_create_task 接线测试：走生产路径验证 done_callback 真实触发。

禁止 mock done_callback——须真实触发 asyncio 事件循环。
"""

import asyncio

import pytest

from src.common.async_utils import _safe_create_task


@pytest.mark.asyncio
async def test_safe_create_task_exception_logs(caplog):
    """task 异常时 done_callback 出声：日志含 task name + 异常类型 + 异常消息。"""

    async def failing():
        raise ValueError("test error")

    caplog.set_level("ERROR", logger="common.async_utils")
    task = _safe_create_task(failing(), name="test-task")

    with pytest.raises(ValueError, match="test error"):
        await task

    await asyncio.sleep(0.01)

    assert any("test-task" in record.message for record in caplog.records), "日志须含 task name"
    assert any(
        record.levelname == "ERROR" and "test-task" in record.message
        for record in caplog.records
    ), "须有 ERROR 级日志含 task name"


@pytest.mark.asyncio
async def test_safe_create_task_cancelled_no_log(caplog):
    """task 被 cancel 时 done_callback 不上报（正常取消语义）。"""

    async def long_running():
        await asyncio.sleep(100)

    caplog.set_level("ERROR", logger="common.async_utils")
    task = _safe_create_task(long_running(), name="cancel-task")

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    await asyncio.sleep(0.01)

    assert not any(
        "cancel-task" in record.message and record.levelname == "ERROR"
        for record in caplog.records
    ), "cancel 不应上报 ERROR"


@pytest.mark.asyncio
async def test_safe_create_task_success_no_log(caplog):
    """task 正常完成时 done_callback 不上报。"""

    async def succeeding():
        return 42

    caplog.set_level("ERROR", logger="common.async_utils")
    task = _safe_create_task(succeeding(), name="success-task")

    result = await task
    assert result == 42

    await asyncio.sleep(0.01)

    assert not any(
        "success-task" in record.message and record.levelname == "ERROR"
        for record in caplog.records
    ), "正常完成不应上报 ERROR"