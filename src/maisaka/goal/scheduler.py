"""Goal 调度器。

定期检查超时 Goal，触发 Goal 评估。
"""

from __future__ import annotations

import asyncio
import logging
import time

from .manager import GoalManager

logger = logging.getLogger(__name__)


class GoalScheduler:
    """Goal 调度器。"""

    CHECK_INTERVAL_SECONDS = 60

    def __init__(self, goal_manager: GoalManager) -> None:
        self._goal_manager = goal_manager
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """启动调度器。"""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Goal调度器已启动")

    async def stop(self) -> None:
        """停止调度器。"""
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Goal调度器已停止")

    async def _run_loop(self) -> None:
        """调度循环。"""
        while self._running:
            try:
                timed_out = self._goal_manager.check_timeouts()
                if timed_out:
                    logger.info("Goal超时检查: 关闭%d个超时Goal", len(timed_out))
            except Exception as e:
                logger.error("Goal超时检查异常: %s", e)

            await asyncio.sleep(self.CHECK_INTERVAL_SECONDS)