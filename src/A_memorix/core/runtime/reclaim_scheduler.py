"""ZG-27 回收调度器（对标 Linux mm/shrinker.c:376 do_shrink_slab）。

Linux 源码参考：
- mm/shrinker.c:376 — do_shrink_slab 两相回收主函数
- mm/shrinker.c:401-403 — delta = (freeable >> priority) * 4 // seeks 压力分级预算
- mm/shrinker.c:413-415 — total_scan = (nr_deferred >> priority) + delta，capped 2*freeable
- mm/shrinker.c:436-437 — while 循环批次回收
- mm/shrinker.c:452 — cond_resched 让出事件循环
- mm/shrinker.c:461-462 — next_deferred = max(0, nr + delta - scanned)，capped 2*freeable
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional

from src.A_memorix.core.runtime.shrinker import (

    SHRINK_EMPTY,
    SHRINK_STOP,
    ShrinkControl,
    Shrinker,
)
from src.common.logger import get_logger

logger = get_logger("a_memorix.reclaim_scheduler")


@dataclass
class ShrinkerRuntimeConfig:
    """shrinker 运行时配置（从 config_schema 读取，复制偏序校验逻辑）。"""

    batch_size: int = 128
    """回收批次大小（对标 SHRINK_BATCH=128）"""
    def_priority: int = 12
    """初始 priority（对标 DEF_PRIORITY）"""


@dataclass
class ReclaimResult:
    """单轮回收结果。"""

    total_freed: int = 0
    per_shrinker_stats: dict = field(default_factory=dict)
    elapsed_ms: float = 0.0


class ReclaimScheduler:
    """回收调度器（对标 Linux mm/shrinker.c:376 do_shrink_slab）。

    遍历已注册 shrinker，按 priority 分级预算调 count/scan 两相。
    单 shrinker 异常不崩溃（spec 4.2 规则 3）。
    """

    def __init__(self, config: ShrinkerRuntimeConfig, error_port=None) -> None:
        self._shrinkers: list[Shrinker] = []
        self._deferred: dict[str, int] = {}
        """nr_deferred 累积（对标 shrinker.c:461-462）"""
        self._config = config
        self._error_port = error_port

    @property
    def config(self) -> ShrinkerRuntimeConfig:
        """只读配置访问（kswapd 读取 def_priority）。"""
        return self._config

    def register(self, shrinker: Shrinker) -> None:
        """注册 shrinker。"""
        self._shrinkers.append(shrinker)
        self._deferred.setdefault(shrinker.name, 0)

    async def _do_shrink_one(self, shrinker: Shrinker, priority: int) -> int:
        """单 shrinker 一轮回收（对标 shrinker.c:376 do_shrink_slab）。

        delta = (freeable >> priority) * 4 // seeks  压力分级预算
        total_scan = (nr_deferred >> priority) + delta，capped 2*freeable
        """
        sc = ShrinkControl(priority=priority)
        freeable = await shrinker.count_objects(sc)
        if freeable == 0 or freeable == SHRINK_EMPTY:
            return 0

        nr = self._deferred.get(shrinker.name, 0)
        seeks = max(1, shrinker.seeks)
        delta = (freeable >> priority) * 4 // seeks
        total_scan = (nr >> priority) + delta
        total_scan = min(total_scan, 2 * freeable)

        batch_size = shrinker.batch or self._config.batch_size
        freed = 0
        scanned = 0
        while total_scan >= batch_size or total_scan >= freeable:
            sc.nr_to_scan = min(batch_size, total_scan)
            sc.nr_scanned = 0
            ret = await shrinker.scan_objects(sc)
            if ret == SHRINK_STOP:
                break
            freed += max(0, ret)
            actual_scanned = sc.nr_scanned if sc.nr_scanned > 0 else sc.nr_to_scan
            total_scan -= actual_scanned
            scanned += actual_scanned
            if total_scan <= 0:
                break
            await asyncio.sleep(0)

        # nr_deferred 累积（对标 shrinker.c:461-462）
        next_deferred = max(0, nr + delta - scanned)
        next_deferred = min(next_deferred, 2 * freeable)
        self._deferred[shrinker.name] = next_deferred
        return freed

    def _report_warning(self, msg: str, exc: Optional[Exception] = None, **extra) -> None:
        """上报 warning（双通道：logger + error_port）。"""
        logger.warning("%s: %s", msg, exc, exc_info=exc is not None, extra=extra)
        if self._error_port is not None:
            try:
                from src.core.error_escalation.types import ErrorLevel

                self._error_port.report(ErrorLevel.WARNING, msg, exception=exc)
            except Exception:
                logger.exception("reclaim_scheduler error_port.report 失败")

    async def run_reclaim(self, priority: int = 12) -> ReclaimResult:
        """遍历已注册 shrinker，按 priority 分级预算调 count/scan 两相。

        单 shrinker 异常不崩溃——上报 warning，跳过该 shrinker（spec 4.2 规则 3）。
        回收超时 > 1000ms 上报 warning 不中断（spec 5.2.3 异常场景 3）。
        """
        start = time.monotonic()
        total_freed = 0
        per_stats: dict[str, dict] = {}
        for shrinker in self._shrinkers:
            try:
                freed = await self._do_shrink_one(shrinker, priority)
                total_freed += freed
                per_stats[shrinker.name] = {"freed": freed, "deferred": self._deferred[shrinker.name]}
            except Exception as exc:
                self._report_warning(f"shrinker {shrinker.name} 回收异常", exc)
                per_stats[shrinker.name] = {"error": str(exc)}
        elapsed_ms = (time.monotonic() - start) * 1000.0
        if elapsed_ms > 1000.0:
            self._report_warning("回收超时", None, elapsed_ms=elapsed_ms)
        return ReclaimResult(total_freed=total_freed, per_shrinker_stats=per_stats, elapsed_ms=elapsed_ms)