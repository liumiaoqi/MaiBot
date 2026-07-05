"""交互引擎定时调度器。

定期遍历所有已注册智能体，评估交互触发。
异常时降级为静默模式，不影响主对话流程。
"""

from __future__ import annotations

import asyncio
import logging

from src.maisaka.agent.registry import AgentConfigRegistry
from src.maisaka.agent_interaction.trigger_scheduler import InteractionTrigger

logger = logging.getLogger(__name__)

_DEFAULT_EVALUATION_INTERVAL = 300  # 5分钟


class InteractionScheduler:
    """交互引擎定时调度器。

    使用 asyncio 定时任务，每隔 evaluation_interval_seconds
    遍历所有已注册智能体，调用 InteractionTrigger.try_trigger。
    """

    def __init__(
        self,
        trigger: InteractionTrigger,
        evaluation_interval_seconds: int = _DEFAULT_EVALUATION_INTERVAL,
    ) -> None:
        self._trigger = trigger
        self._interval = evaluation_interval_seconds
        self._config_registry = AgentConfigRegistry()
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        """启动定时调度。"""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            "[agent_interaction] 调度器启动，评估间隔 %ds", self._interval
        )

    async def stop(self) -> None:
        """停止定时调度。"""
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("[agent_interaction] 调度器已停止")

    async def _run_loop(self) -> None:
        """主调度循环。"""
        while self._running:
            try:
                await self._evaluate_all_agents()
            except Exception:
                logger.exception("[agent_interaction] 调度循环异常，降级静默")
            await asyncio.sleep(self._interval)

    async def _evaluate_all_agents(self) -> None:
        """遍历所有智能体评估交互触发。"""
        agents = self._config_registry.list_agents()
        for agent in agents:
            try:
                result = await self._trigger.try_trigger(agent.agent_id)
                if result is not None and result.success:
                    logger.info(
                        "[agent_interaction] 触发成功: event_id=%s",
                        result.event_id,
                    )
            except Exception:
                logger.warning(
                    "[agent_interaction] 智能体 %s 评估异常，跳过",
                    agent.agent_id,
                    exc_info=True,
                )