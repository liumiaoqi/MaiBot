"""异步写入队列 — 将 observe 调用解耦为 fire-and-forget。

调用方立即获得 pending 结果，写入在后台消费线程中执行。
失败时重试 1 次，仍失败则 ERROR 日志记录。
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

from src.common.logger import get_logger
from src.core.types import MemoryWriteResult

if TYPE_CHECKING:
    from .observer import Observer

logger = get_logger("async_write_queue")

_MAX_RETRIES = 1
_QUEUE_TIMEOUT_SECONDS = 5


class AsyncWriteQueue:
    def __init__(self, observer: Observer, maxsize: int = 100) -> None:
        self._observer = observer
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=maxsize)
        self._consumer_task: asyncio.Task | None = None
        self._stopping = False

    async def start(self) -> None:
        if self._consumer_task is not None and not self._consumer_task.done():
            return
        self._stopping = False
        self._consumer_task = asyncio.create_task(self._consumer(), name="async_write_queue")

    async def stop(self) -> None:
        self._stopping = True
        task = self._consumer_task
        self._consumer_task = None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def enqueue(self, **kwargs: Any) -> MemoryWriteResult:
        """入队写入请求，立即返回 pending 结果。

        队列满时返回失败结果（不阻塞、不丢弃）。
        """
        try:
            self._queue.put_nowait(kwargs)
        except asyncio.QueueFull:
            text_preview = str(kwargs.get("text", ""))[:80]
            logger.warning("async_write_queue 已满（%d），跳过: %s...", self._queue.maxsize, text_preview)
            return MemoryWriteResult(success=False, detail="write_queue_full")
        return MemoryWriteResult(success=True, pending=True)

    async def _consumer(self) -> None:
        try:
            while not self._stopping:
                try:
                    kwargs = await self._queue.get()
                except asyncio.CancelledError:
                    break
                try:
                    await self._write_with_retry(kwargs)
                except Exception:
                    pass
                finally:
                    self._queue.task_done()
        except asyncio.CancelledError:
            pass

    async def _write_with_retry(self, kwargs: dict[str, Any]) -> None:
        last_error: str = ""
        for attempt in range(_MAX_RETRIES + 1):
            try:
                await self._observer.observe(**kwargs)
                return
            except Exception as exc:
                last_error = str(exc)
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(min(1.0, 0.5 * (attempt + 1)))

        text_preview = str(kwargs.get("text", ""))[:120]
        logger.error(
            "async_write_queue 写入失败（重试%d次）: %s | text=%s",
            _MAX_RETRIES, last_error, text_preview,
        )
