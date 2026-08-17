"""ZG-27 测试：shrinker 两相接口（测试组 2——接缝测试）。"""

import pytest

from src.A_memorix.core.runtime.shrinker import (
    SHRINK_EMPTY,

    ShrinkControl,
)


class _InMemoryShrinker:
    """in-memory Shrinker 实现，用于测试。"""

    def __init__(self, name="test", count_ret=0, scan_ret=0, seeks=2, batch=0):
        self.name = name
        self.batch = batch
        self.seeks = seeks
        self.flags = 0
        self._count_ret = count_ret
        self._scan_ret = scan_ret
        self.scan_called = False

    async def count_objects(self, sc: ShrinkControl) -> int:
        return self._count_ret

    async def scan_objects(self, sc: ShrinkControl) -> int:
        self.scan_called = True
        return self._scan_ret


@pytest.mark.asyncio
async def test_shrinker_count_scan_two_phase():
    """count/scan 两相分离：count 返回 0/SHRINK_EMPTY 时 scan 不被调用。"""
    # count 返回 0 → scan 不被调用
    s = _InMemoryShrinker(count_ret=0)
    sc = ShrinkControl()
    result = await s.count_objects(sc)
    assert result == 0
    assert not s.scan_called

    # count 返回非零 → scan 被调用
    s = _InMemoryShrinker(count_ret=100, scan_ret=50)
    sc = ShrinkControl()
    result = await s.count_objects(sc)
    assert result == 100
    ret = await s.scan_objects(sc)
    assert s.scan_called
    assert ret == 50

    # count 返回 SHRINK_EMPTY → scan 不被调用
    s = _InMemoryShrinker(count_ret=SHRINK_EMPTY)
    sc = ShrinkControl()
    result = await s.count_objects(sc)
    assert result == SHRINK_EMPTY
    assert not s.scan_called