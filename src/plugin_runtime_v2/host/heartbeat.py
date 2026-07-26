"""心跳保活管理器 — Host 端使用。

通过 asyncio.Task 定时发送 HeartbeatRequest，
连续超时后判定 Runner 断开。
"""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

from src.common.logger import get_logger

logger = get_logger("plugin_runtime_v2.host.heartbeat")


class HeartbeatManager:
    """心跳保活管理器。

    为每个 Runner 维护独立的 asyncio.Task 定时器，
    通过回调向 Runner 发送心跳请求，连续超时后触发断开回调。
    """

    def __init__(self, interval_s: int, timeout_s: int, max_misses: int) -> None:
        self._interval_s = interval_s
        self._timeout_s = timeout_s
        self._max_misses = max_misses
        self._tasks: dict[str, asyncio.Task] = {}
        self._response_events: dict[str, asyncio.Event] = {}
        self._miss_counts: dict[str, int] = {}

    def start(
        self,
        runner_id: str,
        send_callback: Callable[[], Awaitable[None]],
        timeout_callback: Callable[[str], Awaitable[None]],
    ) -> None:
        """为指定 runner_id 启动心跳定时器。

        Args:
            runner_id: Runner 标识
            send_callback: 发送 HeartbeatRequest 的异步回调
            timeout_callback: 连续超时判定断开后的异步回调
        """
        if runner_id in self._tasks:
            return
        self._response_events[runner_id] = asyncio.Event()
        self._miss_counts[runner_id] = 0
        self._tasks[runner_id] = asyncio.create_task(
            self._heartbeat_loop(runner_id, send_callback, timeout_callback),
            name=f"heartbeat-{runner_id}",
        )

    def stop(self, runner_id: str) -> None:
        """停止指定 runner_id 的心跳任务。"""
        task = self._tasks.pop(runner_id, None)
        if task is not None:
            task.cancel()
        self._response_events.pop(runner_id, None)
        self._miss_counts.pop(runner_id, None)

    def stop_all(self) -> None:
        """停止全部心跳任务。"""
        for runner_id in list(self._tasks.keys()):
            self.stop(runner_id)

    def record_response(self, runner_id: str) -> None:
        """记录一次成功的心跳响应，重置丢失计数。"""
        self._miss_counts[runner_id] = 0
        event = self._response_events.get(runner_id)
        if event is not None:
            event.set()

    async def _heartbeat_loop(
        self,
        runner_id: str,
        send_callback: Callable[[], Awaitable[None]],
        timeout_callback: Callable[[str], Awaitable[None]],
    ) -> None:
        """单 Runner 心跳循环。"""
        try:
            while runner_id in self._tasks:
                await asyncio.sleep(self._interval_s)
                if runner_id not in self._tasks:
                    return

                try:
                    await send_callback()
                except Exception as exc:
                    logger.warning(
                        "Runner %s 发送心跳请求失败，计入丢失", runner_id
                    )

                event = self._response_events.get(runner_id)
                if event is None:
                    return
                event.clear()

                try:
                    await asyncio.wait_for(event.wait(), timeout=self._timeout_s)
                    # 收到响应 — 计数由 record_response 重置
                except asyncio.TimeoutError:
                    miss_count = self._miss_counts.get(runner_id, 0)
                    if miss_count < self._max_misses:
                        miss_count += 1
                        self._miss_counts[runner_id] = miss_count
                        logger.warning(
                            "Runner %s 心跳响应超时（第 %d/%d 次）",
                            runner_id, miss_count, self._max_misses,
                        )
                    if miss_count >= self._max_misses:
                        logger.warning(
                            "Runner %s 心跳连续超时 %d 次，判定断开",
                            runner_id, miss_count,
                        )
                        await timeout_callback(runner_id)
                        return
        except asyncio.CancelledError:
            pass
