"""SoftirqBatcher — 事件回调预算组件（对标 Linux ksoftirqd）

核心思想（对标 Linux softirq/ksoftirqd）：
- raise_softirq 只入队不处理（对标 raise_softirq 置 pending 位）
- 独立 drainer Task 批量消费（对标 ksoftirqd 线程）
- 单轮时间 + 数量双预算（对标 MAX_SOFTIRQ_TIME=2ms / MAX_SOFTIRQ_RESTART=10）

边界（不解决，属 ZG-18 rescuer 域）：
- CPU 密集回调（无 await 挂起点的纯计算）耗时是计算本身，批处理仅省 Task 调度开销（1.04-1.3×），
  不在本组件能力范围——CPU 密集风暴归 ZG-18 worker 卡死恢复处理。
- 拦截型 handler（需同步顺序执行、可修改消息/参与投票）不适用本组件，由调用方自行同步处理。

线程安全：raise_softirq 可从任意线程调用（deque + threading.Lock + call_soon_threadsafe 唤醒）。
"""

import asyncio
import threading
import time
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Awaitable, Callable, Generic, TypeVar

from src.common.logger import get_logger

logger = get_logger("core.softirq_batcher")

T = TypeVar("T")


class SchedulingStrategy(Enum):
    """批内调度策略"""

    FIFO = "fifo"            # 先入先出（兼容保留）
    TWO_QUEUE = "two_queue"  # 轻任务优先 + 重任务老化
    HRRN = "hrrn"            # 最高响应比优先（默认，最平衡）


@dataclass
class SoftirqItem(Generic[T]):
    """入队条目：payload + 入队时刻（毫秒）+ 轻重分级标记"""

    payload: T
    enqueued_at: float       # time.perf_counter() * 1000，等待时间计算基准
    is_heavy: bool = False   # 轻/重分级（two_queue/hrrn 用，无分级信息时退化为等价 fifo）


def _now_ms() -> float:
    """当前时刻（毫秒）"""
    return time.perf_counter() * 1000.0


class SoftirqBatcher(Generic[T]):
    """ksoftirqd 等效：回调只入队 + 批量处理有预算

    对标 Linux softirq/ksoftirqd：
    - raise_softirq ≈ raise_softirq（只置 pending 位，轻量）
    - _drain_loop ≈ ksoftirqd 线程主循环
    - _drain_once ≈ handle_softirqs 单轮预算处理

    预算参数（实验推荐默认值，对标 MAX_SOFTIRQ_TIME=2ms）：
    - budget_ms=2.0：单轮时间预算（软约束，保险作用）
    - budget_count=200：单轮数量预算（强约束）

    调度策略（实验实测）：
    - hrrn（默认）：响应比排序，最平衡（light p95≈0.24ms，heavy p50≈2.3ms）
    - two_queue：轻任务绝对优先 + 重任务老化
    - fifo：先入先出（兼容保留，有队头阻塞）
    """

    def __init__(
        self,
        handler: Callable[[list[T]], Awaitable[None]],
        budget_ms: float = 2.0,
        budget_count: int = 200,
        strategy: SchedulingStrategy = SchedulingStrategy.HRRN,
        heavy_service_ms: float = 10.0,
        aging_threshold_ms: float = 30.0,
    ) -> None:
        self._handler = handler
        self._budget_ms = budget_ms
        self._budget_count = budget_count
        self._strategy = strategy
        self._heavy_service_ms = heavy_service_ms
        self._aging_threshold_ms = aging_threshold_ms

        self._pending: deque[SoftirqItem[T]] = deque()
        self._lock = threading.Lock()
        self._wakeup = asyncio.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._drainer: asyncio.Task[None] | None = None

        # 策略函数表（避免 if/elif 蔓延）
        self._pickers: dict[SchedulingStrategy, Callable[[int], list[SoftirqItem[T]]]] = {
            SchedulingStrategy.FIFO: self._pick_fifo,
            SchedulingStrategy.TWO_QUEUE: self._pick_two_queue,
            SchedulingStrategy.HRRN: self._pick_hrrn,
        }

    def queue_size(self) -> int:
        """当前积压条目数（可观测）"""
        with self._lock:
            return len(self._pending)

    def raise_softirq(self, item: T, is_heavy: bool = False) -> None:
        """轻量入队（对标 raise_softirq 只置 pending 位）

        不执行回调、不创建逐条 Task、不 await。线程安全：可从任意线程调用。
        """
        with self._lock:
            self._pending.append(SoftirqItem(item, enqueued_at=_now_ms(), is_heavy=is_heavy))
        self._wakeup_drainer()

    def _wakeup_drainer(self) -> None:
        """唤醒 drainer（双路径：事件循环线程直连 / 跨线程 call_soon_threadsafe）

        loop 未运行/未绑定时只入队不唤醒（条目滞留，待 start 后消费）。
        """
        loop = self._loop
        if loop is None:
            # drainer 未创建：尝试惰性兜底
            self._lazy_start()
            return
        # 判断当前是否事件循环线程
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is loop:
            # 事件循环线程内：直连快路径
            self._wakeup.set()
        else:
            # 跨线程：call_soon_threadsafe
            try:
                loop.call_soon_threadsafe(self._wakeup.set)
            except RuntimeError:
                # loop 已关闭：仅入队，不唤醒
                pass

    def _lazy_start(self) -> None:
        """惰性兜底：检测到 running loop 且 drainer 为 None 时自动启动"""
        if self._drainer is not None and not self._drainer.done():
            return
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return  # 无 running loop，不启动
        # 有 running loop 但 drainer 未启动——自动 start
        # 注意：此处可能在非事件循环线程检测到 running loop，
        # 但 create_task 必须在事件循环线程调用，故仅当当前线程即事件循环线程时启动
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            return
        if self._loop is not None and running is self._loop:
            self.start()

    def start(self) -> None:
        """启动 drainer Task（必须在事件循环运行后调用，幂等）"""
        if self._drainer is not None and not self._drainer.done():
            return  # 幂等
        self._loop = asyncio.get_running_loop()
        self._drainer = asyncio.create_task(self._drain_loop())
        # 若有积压（start 前入队的条目），唤醒 drainer 立即消费
        if self.queue_size() > 0:
            self._wakeup.set()
        logger.debug("SoftirqBatcher drainer 已启动 strategy=%s budget_ms=%s budget_count=%s",
                     self._strategy.value, self._budget_ms, self._budget_count)

    async def stop(self) -> None:
        """停止 drainer（吸收 CancelledError，积压不再处理，无悬挂 Task）"""
        drainer = self._drainer
        if drainer is None:
            return
        drainer.cancel()
        try:
            await drainer
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.ERROR, "SoftirqBatcher drainer 停止时异常", exception=exc)
            logger.exception("SoftirqBatcher drainer 停止时异常")
        self._drainer = None
        logger.debug("SoftirqBatcher drainer 已停止 剩余积压=%d", self.queue_size())

    async def _drain_loop(self) -> None:
        """ksoftirqd 等效：等唤醒 → 处理 → 等唤醒（不忙轮询）"""
        while True:
            await self._wakeup.wait()
            self._wakeup.clear()
            await self._drain_once()

    async def _drain_once(self) -> None:
        """单轮预算处理：取批（数量强约束 + 时间软约束）→ 批量 handler（异常隔离）→ 积压续处理"""
        loop = self._loop or asyncio.get_event_loop()
        deadline = loop.time() + self._budget_ms / 1000.0
        batch = self._pick_batch(self._budget_count, deadline)
        if not batch:
            # 取批为空但队列非空（如 two_queue 全部 heavy 未老化）：唤醒重试避免死锁
            if self.queue_size() > 0:
                self._wakeup.set()
            return
        payloads = [item.payload for item in batch]
        try:
            await self._handler(payloads)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.ERROR, "SoftirqBatcher 批量处理异常", exception=exc)
            # 批量 handler 异常：记录并继续下一轮，drainer 主循环不退出
            logger.exception("SoftirqBatcher 批量处理异常 batch_size=%d", len(payloads))
        # 积压续处理（对标 wakeup_softirqd）
        if self.queue_size() > 0:
            self._wakeup.set()

    def _pick_batch(self, limit: int, deadline: float) -> list[SoftirqItem[T]]:
        """取批：策略函数表分派 + 时间预算软约束"""
        picker = self._pickers[self._strategy]
        with self._lock:
            if not self._pending:
                return []
            picked = picker(limit)
            # 时间预算软约束：超 deadline 则截断（已取的仍处理，未取的留队）
            loop = self._loop
            if loop is not None and loop.time() >= deadline and len(picked) > 1:
                # 保留至少 1 条避免空转
                keep = picked[:1]
                # 未取的放回队头（保持原顺序）
                for item in reversed(picked[1:]):
                    self._pending.appendleft(item)
                picked = keep
            return picked

    def _pick_fifo(self, limit: int) -> list[SoftirqItem[T]]:
        """FIFO：队头顺序取批"""
        picked: list[SoftirqItem[T]] = []
        while self._pending and len(picked) < limit:
            picked.append(self._pending.popleft())
        return picked

    def _pick_two_queue(self, limit: int) -> list[SoftirqItem[T]]:
        """two_queue：轻任务直接取批；重任务仅当等待 ≥ 老化阈值时取"""
        now = _now_ms()
        picked: list[SoftirqItem[T]] = []
        remaining: list[SoftirqItem[T]] = []
        while self._pending:
            item = self._pending.popleft()
            if not item.is_heavy:
                picked.append(item)
                if len(picked) >= limit:
                    remaining.extend(self._pending)
                    self._pending.clear()
                    break
            else:
                wait = now - item.enqueued_at
                if wait >= self._aging_threshold_ms:
                    picked.append(item)
                    if len(picked) >= limit:
                        remaining.extend(self._pending)
                        self._pending.clear()
                        break
                else:
                    remaining.append(item)  # 未老化的重任务留队
        # 兜底：全部未老化 heavy 时强制取队头一条避免空转
        if not picked and remaining:
            picked.append(remaining.pop(0))
        # 剩余放回（保持顺序）
        for item in reversed(remaining):
            self._pending.appendleft(item)
        return picked

    def _pick_hrrn(self, limit: int) -> list[SoftirqItem[T]]:
        """HRRN：响应比 R=(等待+服务)/服务 降序取前 limit 条，剩余放回"""
        now = _now_ms()
        items = list(self._pending)
        self._pending.clear()
        if not items:
            return []
        # 计算响应比
        def response_ratio(item: SoftirqItem[T]) -> float:
            wait = now - item.enqueued_at
            size = self._heavy_service_ms if item.is_heavy else 1.0
            return (wait + size) / size
        items.sort(key=response_ratio, reverse=True)
        picked = items[:limit]
        remaining = items[limit:]
        # 剩余放回（按响应比降序，保持下次取批的一致性）
        for item in reversed(remaining):
            self._pending.appendleft(item)
        return picked

    def remove_matching(self, predicate: Callable[[SoftirqItem[T]], bool]) -> int:
        """按谓词移除队列中未处理条目（支撑 cancel_handler_tasks 语义）

        已取入批中执行的条目无法中途移除（与"已完成任务不可取消"语义等价）。
        返回移除条数。
        """
        with self._lock:
            kept: list[SoftirqItem[T]] = []
            removed = 0
            while self._pending:
                item = self._pending.popleft()
                if predicate(item):
                    removed += 1
                else:
                    kept.append(item)
            self._pending.extend(kept)
            return removed