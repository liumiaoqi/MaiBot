"""ZG-27 测试：kswapd 后台任务（测试组 5——接缝测试）。"""

import pytest

from src.A_memorix.core.runtime.kswapd import MemoryKswapd
from src.A_memorix.core.runtime.reclaim_scheduler import (
    ReclaimScheduler,
    ShrinkerRuntimeConfig,
)
from src.A_memorix.core.runtime.watermark import (
    WatermarkConfig,
    WatermarkZone,
)


class _FakeBackgroundScheduler:
    """fake background_scheduler——实现 stopping 属性。"""

    def __init__(self):
        self.stopping = False


@pytest.mark.asyncio
async def test_kswapd_wakeup_on_below_low():
    """BELOW_LOW → 调 ReclaimScheduler.run_reclaim。"""
    zone = WatermarkZone(WatermarkConfig(min=100, low=200, high=400), usage_provider=lambda: 150)
    sched = ReclaimScheduler(ShrinkerRuntimeConfig())
    bg = _FakeBackgroundScheduler()
    kswapd = MemoryKswapd(zone, sched, bg)

    run_reclaim_called = False
    original = sched.run_reclaim

    async def spy_run_reclaim(priority=12):
        nonlocal run_reclaim_called
        run_reclaim_called = True
        return await original(priority=priority)

    sched.run_reclaim = spy_run_reclaim
    await kswapd._run_one_cycle()
    assert run_reclaim_called


@pytest.mark.asyncio
async def test_kswapd_sleep_on_above_high():
    """ABOVE_HIGH → 不调 ReclaimScheduler.run_reclaim。"""
    zone = WatermarkZone(WatermarkConfig(min=100, low=200, high=400), usage_provider=lambda: 500)
    sched = ReclaimScheduler(ShrinkerRuntimeConfig())
    bg = _FakeBackgroundScheduler()
    kswapd = MemoryKswapd(zone, sched, bg)

    run_reclaim_called = False

    async def spy_run_reclaim(priority=12):
        nonlocal run_reclaim_called
        run_reclaim_called = True
        return None

    sched.run_reclaim = spy_run_reclaim
    await kswapd._run_one_cycle()
    assert not run_reclaim_called


@pytest.mark.asyncio
async def test_kswapd_exception_no_crash():
    """usage_provider 异常不崩溃——warning + 不抛异常。"""
    def bad_provider():
        raise RuntimeError("boom")

    zone = WatermarkZone(WatermarkConfig(min=100, low=200, high=400), usage_provider=bad_provider)
    sched = ReclaimScheduler(ShrinkerRuntimeConfig())
    bg = _FakeBackgroundScheduler()
    kswapd = MemoryKswapd(zone, sched, bg)
    await kswapd._run_one_cycle()


@pytest.mark.asyncio
async def test_kswapd_reclaim_to_high_then_stop():
    """P2-12: BELOW_LOW → 回收到 ABOVE_HIGH 后停止 priority 递减。"""
    # usage 从 150（BELOW_LOW）开始，每次 run_reclaim 后模拟降到 500（ABOVE_HIGH）
    usage = [150]
    zone = WatermarkZone(WatermarkConfig(min=100, low=200, high=400), usage_provider=lambda: usage[0])
    sched = ReclaimScheduler(ShrinkerRuntimeConfig())
    bg = _FakeBackgroundScheduler()
    kswapd = MemoryKswapd(zone, sched, bg)

    reclaim_count = 0

    async def spy_run_reclaim(priority=12):
        nonlocal reclaim_count
        reclaim_count += 1
        usage[0] = 500  # 模拟回收后水位升到 ABOVE_HIGH

    sched.run_reclaim = spy_run_reclaim
    await kswapd._run_one_cycle()
    assert reclaim_count == 1  # 回收一次后 ABOVE_HIGH → 停止


@pytest.mark.asyncio
async def test_kswapd_def_priority_from_config():
    """P2-8: kswapd 使用 config.def_priority 而非硬编码 12。"""
    zone = WatermarkZone(WatermarkConfig(min=100, low=200, high=400), usage_provider=lambda: 150)
    sched = ReclaimScheduler(ShrinkerRuntimeConfig(def_priority=8))
    bg = _FakeBackgroundScheduler()
    kswapd = MemoryKswapd(zone, sched, bg)

    priorities_used = []

    async def spy_run_reclaim(priority=12):
        priorities_used.append(priority)
        return None

    sched.run_reclaim = spy_run_reclaim
    await kswapd._run_one_cycle()
    assert priorities_used[0] == 8  # 使用 config 中的 def_priority=8
