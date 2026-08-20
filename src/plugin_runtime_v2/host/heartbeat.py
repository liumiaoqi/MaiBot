"""心跳保活管理器 — Host 端使用。

通过 asyncio.Task 定时发送 HeartbeatRequest，
连续超时后判定 Runner 断开。
"""


import asyncio
import inspect
from typing import Any, Awaitable, Callable, Optional

from src.common.async_utils import _safe_create_task
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
        self._timeout_listeners: dict[
            str, set[Callable[[str, Optional[dict[str, Any]]], Awaitable[None]]]
        ] = {}

    def start(
        self,
        runner_id: str,
        send_callback: Callable[[], Awaitable[None]],
        timeout_callback: Callable[[str, Optional[dict[str, Any]]], Awaitable[None]],
    ) -> None:
        """为指定 runner_id 启动心跳定时器。

        Args:
            runner_id: Runner 标识
            send_callback: 发送 HeartbeatRequest 的异步回调
            timeout_callback: 连续超时判定断开后的异步回调。
                支持两种签名（向后兼容）：
                - 旧签名: Callable[[str], Awaitable[None]] — 仅接收 runner_id
                - 新签名: Callable[[str, Optional[dict]], Awaitable[None]] — 额外接收上下文
        """
        if runner_id in self._tasks:
            return
        self._response_events[runner_id] = asyncio.Event()
        self._miss_counts[runner_id] = 0
        self._tasks[runner_id] = _safe_create_task(
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
        self._timeout_listeners.pop(runner_id, None)

    def add_timeout_listener(
        self,
        runner_id: str,
        listener: Callable[[str, Optional[dict[str, Any]]], Awaitable[None]],
    ) -> None:
        """为该 runner 注册心跳超时旁路监听器。

        前置条件：无（不依赖 start 是否已调用，start 前/后均可注册）。
        后置条件：该 runner 心跳连续超时判定时，listener(runner_id, context)
        在原始回调之前被调用；同一可调用对象重复注册不产生重复调用
        （set 去重）；listener 在 stop(runner_id) 时随任务一并清理。
        """
        self._timeout_listeners.setdefault(runner_id, set()).add(listener)

    def remove_timeout_listener(
        self,
        runner_id: str,
        listener: Callable[[str, Optional[dict[str, Any]]], Awaitable[None]],
    ) -> None:
        """移除该 runner 的指定心跳超时监听器。不存在时静默忽略。"""
        listeners = self._timeout_listeners.get(runner_id)
        if listeners is None:
            return
        listeners.discard(listener)
        if not listeners:
            self._timeout_listeners.pop(runner_id, None)

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
        timeout_callback: Callable[[str, Optional[dict[str, Any]]], Awaitable[None]],
    ) -> None:
        """单 Runner 心跳循环。"""
        # 向后兼容：探测 timeout_callback 接受的参数数量
        try:
            sig = inspect.signature(timeout_callback)
            callback_param_count = len(sig.parameters)
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, "检测 timeout_callback 签名失败", exception=exc)
            callback_param_count = 1
            logger.warning("无法检测 timeout_callback 签名，按旧签名(1参数)调用")
        try:
            while runner_id in self._tasks:
                await asyncio.sleep(self._interval_s)
                if runner_id not in self._tasks:
                    return

                try:
                    await send_callback()
                except Exception as exc:
                    from src.core.error_escalation.types import ErrorLevel
                    from src.core.error_escalation_port_registry import get_error_escalation_port
                    port = get_error_escalation_port()
                    if port is not None:
                        port.report(ErrorLevel.WARNING, "发送心跳请求失败，计入丢失", exception=exc)
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
                        context = {
                            "detection_source": "heartbeat",
                            "consecutive_failures": miss_count,
                        }
                        # 旁路监听器优先执行（W1：原始回调经 context.abort
                        # 必然抛异常不返回，监听器必须在其之前执行，否则永不触发）
                        for listener in tuple(
                            self._timeout_listeners.get(runner_id, ())
                        ):
                            try:
                                await listener(runner_id, context)
                            except Exception as exc:
                                from src.core.error_escalation.types import ErrorLevel
                                from src.core.error_escalation_port_registry import get_error_escalation_port
                                port = get_error_escalation_port()
                                if port is not None:
                                    port.report(ErrorLevel.ERROR, "插件心跳循环异常", exception=exc)
                                logger.exception(
                                    "心跳监听器异常（runner_id=%s）", runner_id
                                )
                        # 向后兼容：按签名探测结果选择调用方式
                        if callback_param_count >= 2:
                            await timeout_callback(runner_id, context)
                        else:
                            await timeout_callback(runner_id)
                        return
        except asyncio.CancelledError:
            # P0-4: 正常取消静默（防刷屏，对标 kernel/signal.c TASK_KILLABLE）
            pass
        except Exception as exc:
            # P0-2: 心跳循环异常出声（ZG-31）
            # 对标 Linux kernel/panic.c:77-92 OOPS + dsh defensive-patterns: Contain callback exceptions in the dispatcher
            logger.exception("heartbeat loop failed (runner_id=%s): %s", runner_id, exc, exc_info=True)
