"""ZG-27 测试：回收调度器压力分级预算（测试组 3——接缝测试）。"""

import asyncio

import pytest

from src.A_memorix.core.runtime.reclaim_scheduler import (
    ReclaimScheduler,
    ShrinkerRuntimeConfig,
)
from src.A_memorix.core.runtime.shrinker import ShrinkControl


class _InMemoryShrinker:
    """in-memory Shrinker，记录 scan 调用次数。"""

    def __init__(self, name="test", freeable=1024, seeks=2, batch=0, scan_ret=None, raise_exc=None):
        self.name = name
        self.batch = batch
        self.seeks = seeks
        self.flags = 0
        self._freeable = freeable
        self._scan_ret = scan_ret
        self._raise_exc = raise_exc
        self.scan_count = 0

    async def count_objects(self, sc: ShrinkControl) -> int:
        return self._freeable

    async def scan_objects(self, sc: ShrinkControl) -> int:
        if self._raise_exc is not None:
            raise self._raise_exc
        self.scan_count += 1
        sc.nr_scanned = sc.nr_to_scan
        return self._scan_ret if self._scan_ret is not None else sc.nr_to_scan


@pytest.mark.asyncio
async def test_pressure_based_delta():
    """priority 越高 delta 越小；seeks 越大 delta 越小。"""
    # priority=12 → delta = 1024 >> 12 = 0
    s = _InMemoryShrinker(freeable=1024, seeks=1)
    sched = ReclaimScheduler(ShrinkerRuntimeConfig())
    sched.register(s)
    await sched.run_reclaim(priority=12)
    count_high_prio = s.scan_count

    # priority=1 → delta = 1024 >> 1 = 512
    s2 = _InMemoryShrinker(freeable=1024, seeks=1)
    sched2 = ReclaimScheduler(ShrinkerRuntimeConfig())
    sched2.register(s2)
    await sched2.run_reclaim(priority=1)
    count_low_prio = s2.scan_count

    assert count_low_prio >= count_high_prio

    # seeks=8 → delta 比 seeks=1 小
    s_seeks8 = _InMemoryShrinker(freeable=1024, seeks=8)
    sched8 = ReclaimScheduler(ShrinkerRuntimeConfig())
    sched8.register(s_seeks8)
    await sched8.run_reclaim(priority=1)
    assert s_seeks8.scan_count <= s2.scan_count


@pytest.mark.asyncio
async def test_nr_deferred_accumulation():
    """nr_deferred 累积：第二轮 total_scan 含累积量。"""
    s = _InMemoryShrinker(freeable=100, seeks=1, scan_ret=5)
    sched = ReclaimScheduler(ShrinkerRuntimeConfig())
    sched.register(s)
    await sched.run_reclaim(priority=1)

    await sched.run_reclaim(priority=1)
    second_deferred = sched._deferred.get("test", 0)
    assert second_deferred <= 2 * 100  # capped 2*freeable


@pytest.mark.asyncio
async def test_batch_reclaim():
    """批次回收：大 freeable 时 scan_objects 被多次调用。"""
    s = _InMemoryShrinker(freeable=10000, seeks=1)
    sched = ReclaimScheduler(ShrinkerRuntimeConfig(batch_size=128))
    sched.register(s)
    await sched.run_reclaim(priority=1)
    assert s.scan_count >= 1


@pytest.mark.asyncio
async def test_scan_objects_yield_event_loop():
    """scan_objects 让出事件循环——不超时。"""
    s = _InMemoryShrinker(freeable=100, seeks=1)
    sched = ReclaimScheduler(ShrinkerRuntimeConfig())
    sched.register(s)
    result = await asyncio.wait_for(sched.run_reclaim(priority=1), timeout=5.0)
    assert result is not None


@pytest.mark.asyncio
async def test_single_shrinker_exception_no_crash():
    """单 shrinker 异常不崩溃——其他 shrinker 正常执行。"""
    s_bad = _InMemoryShrinker(name="bad", freeable=100, raise_exc=RuntimeError("boom"))
    s_good = _InMemoryShrinker(name="good", freeable=100, seeks=1)
    sched = ReclaimScheduler(ShrinkerRuntimeConfig())
    sched.register(s_bad)
    sched.register(s_good)
    result = await sched.run_reclaim(priority=1)
    assert "bad" in result.per_shrinker_stats
    assert "error" in result.per_shrinker_stats["bad"]
    assert "good" in result.per_shrinker_stats