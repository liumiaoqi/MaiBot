"""并行思考调度器 — 管理多个智能体的并行思考。

使用 asyncio.Semaphore 控制并发数，避免同时发起过多 LLM 请求。
"""

from __future__ import annotations

import asyncio

from src.common.logger import get_logger
from src.core.protocols import ThinkingOrgan
from src.core.types import ThinkContext, ThinkResult

logger = get_logger("agent_autonomy.parallel_think")


class ParallelThinkScheduler:
    """并行思考调度器 — 管理多个智能体的并行思考。"""

    def __init__(self, max_concurrent: int = 2) -> None:
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._pending: dict[str, asyncio.Task[ThinkResult]] = {}

    async def schedule(
        self,
        agent_id: str,
        organ: ThinkingOrgan,
        context: ThinkContext,
    ) -> asyncio.Task[ThinkResult]:
        """调度一次思考（可能并行执行）。

        Returns:
            思考结果的 asyncio.Task，可 await 获取结果
        """
        if agent_id in self._pending and not self._pending[agent_id].done():
            self._pending[agent_id].cancel()

        task = asyncio.create_task(self._run_think(agent_id, organ, context))
        self._pending[agent_id] = task
        return task

    async def schedule_proactive(
        self,
        agent_id: str,
        organ: ThinkingOrgan,
        reason: str,
        context: ThinkContext,
    ) -> asyncio.Task[ThinkResult]:
        """调度一次主动思考。"""
        if agent_id in self._pending and not self._pending[agent_id].done():
            self._pending[agent_id].cancel()

        task = asyncio.create_task(self._run_think_proactive(agent_id, organ, reason, context))
        self._pending[agent_id] = task
        return task

    async def _run_think(
        self,
        agent_id: str,
        organ: ThinkingOrgan,
        context: ThinkContext,
    ) -> ThinkResult:
        async with self._semaphore:
            try:
                return await organ.think(context)
            except asyncio.CancelledError:
                return ThinkResult(action=ThinkAction.SILENT)
            except Exception as exc:
                logger.error(f"[parallel_think] 思考异常: agent={agent_id} error={exc}")
                return ThinkResult(action=ThinkAction.ERROR, error_message=str(exc))

    async def _run_think_proactive(
        self,
        agent_id: str,
        organ: ThinkingOrgan,
        reason: str,
        context: ThinkContext,
    ) -> ThinkResult:
        async with self._semaphore:
            try:
                return await organ.think_proactive(reason, context)
            except asyncio.CancelledError:
                return ThinkResult(action=ThinkAction.SILENT)
            except Exception as exc:
                logger.error(f"[parallel_think] 主动思考异常: agent={agent_id} error={exc}")
                return ThinkResult(action=ThinkAction.ERROR, error_message=str(exc))

    async def wait_all(self) -> dict[str, ThinkResult]:
        """等待所有待处理思考完成，返回 agent_id → ThinkResult 映射。"""
        if not self._pending:
            return {}

        results: dict[str, ThinkResult] = {}
        for agent_id, task in list(self._pending.items()):
            if task.done():
                try:
                    results[agent_id] = task.result()
                except Exception:
                    results[agent_id] = ThinkResult(action=ThinkAction.ERROR, error_message="task failed")
            else:
                try:
                    results[agent_id] = await task
                except Exception:
                    results[agent_id] = ThinkResult(action=ThinkAction.ERROR, error_message="task failed")

        self._pending.clear()
        return results

    def cancel(self, agent_id: str) -> None:
        """取消指定智能体的待处理思考。"""
        task = self._pending.pop(agent_id, None)
        if task is not None and not task.done():
            task.cancel()