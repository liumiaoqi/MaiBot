from __future__ import annotations

import asyncio
from typing import Any, Callable, Coroutine, Dict

from src.common.logger import get_logger

logger = get_logger("a_memorix.services.background_scheduler")


class BackgroundTaskScheduler:
    """后台任务调度器 — 从 SDKMemoryKernel 提取。"""

    def __init__(self) -> None:
        self._tasks: Dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()
        self._stopping: bool = False

    @property
    def stopping(self) -> bool:
        return self._stopping

    def ensure_task(self, name: str, factory: Callable[[], Coroutine[Any, Any, None]]) -> None:
        task = self._tasks.get(name)
        if task is not None and not task.done():
            return
        self._tasks[name] = asyncio.create_task(factory(), name=f"A_Memorix.{name}")

    async def start_all(self, registrations: Dict[str, Callable[[], Coroutine[Any, Any, None]]]) -> None:
        async with self._lock:
            self._stopping = False
            for name, factory in registrations.items():
                self.ensure_task(name, factory)

    async def stop_all(self) -> None:
        async with self._lock:
            self._stopping = True
            tasks = [task for task in self._tasks.values() if task is not None and not task.done()]
            for task in tasks:
                task.cancel()
            for task in tasks:
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                except Exception as exc:
                    logger.warning(f"后台任务退出异常: {exc}")
            self._tasks.clear()

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(max(0.0, float(seconds or 0.0)))