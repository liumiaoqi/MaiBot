"""统一异步工具：fire-and-forget task 安全创建封装。

_safe_create_task 替代裸 asyncio.create_task，通过 done_callback 确保
task 异常不会静默丢失——异常时 logger.error + error_escalation_port 上报。
"""

import asyncio
from collections.abc import Coroutine
from typing import Any, TypeVar

from src.common.logger import get_logger

logger = get_logger("common.async_utils")

T = TypeVar("T")


def _make_safe_callback(task_name: str):
    """构造 done_callback：task 异常时出声上报。"""

    def _callback(task: asyncio.Task[Any]) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc is None:
            return
        logger.error("fire-and-forget task 异常: name=%s", task_name, exc_info=exc)
        try:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port

            port = get_error_escalation_port()
            if port is not None:
                port.report(
                    ErrorLevel.ERROR,
                    f"fire-and-forget task 异常: name={task_name}",
                    exception=exc,
                )
        except Exception:
            logger.error("error_port.report 失败 (task_name=%s)", task_name, exc_info=exc)

    return _callback


def _safe_create_task(
    coro: Coroutine[Any, Any, T],
    *,
    name: str,
) -> asyncio.Task[T]:
    """安全创建 fire-and-forget task：异常时 done_callback 上报。

    替代裸 asyncio.create_task——通过 add_done_callback 确保 task 异常
    不会静默丢失。cancelled 任务不上报（正常取消语义）。

    Args:
        coro: 协程对象
        name: task 名称（用于日志定位，必填）

    Returns:
        asyncio.Task 实例
    """
    task = asyncio.create_task(coro, name=name)
    task.add_done_callback(_make_safe_callback(name))
    return task