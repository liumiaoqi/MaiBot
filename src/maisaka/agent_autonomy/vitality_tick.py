"""生命力心跳调度器——周期性触发待命智能体的生命力评估。"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from src.common.logger import get_logger
from src.config.config import global_config

if TYPE_CHECKING:
    from src.maisaka.agent_autonomy.vitality_manager import VitalityManager

logger = get_logger("agent_autonomy.vitality_tick")


class VitalityTickScheduler:
    """生命力心跳调度器。"""

    def __init__(
        self,
        vitality_manager: VitalityManager,
        interval_seconds: int | None = None,
    ) -> None:
        self._vitality_manager = vitality_manager
        self._interval = interval_seconds or global_config.agent_autonomy.vitality_tick_interval_seconds
        self._task: asyncio.Task | None = None
        self._running = False

    def start(self) -> None:
        """启动心跳周期任务。"""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._tick_loop())
        logger.info(f"[vitality_tick] 心跳调度器启动: interval={self._interval}s")

    def stop(self) -> None:
        """停止心跳周期任务。"""
        self._running = False
        if self._task is not None:
            self._task.cancel()
            self._task = None
        logger.info("[vitality_tick] 心跳调度器停止")

    @property
    def is_running(self) -> bool:
        return self._running

    async def _tick_loop(self) -> None:
        """心跳循环。"""
        while self._running:
            try:
                await asyncio.sleep(self._interval)
                await self._vitality_manager.evaluate_vitality_tick()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning(f"[vitality_tick] 心跳评估异常: error={exc}")