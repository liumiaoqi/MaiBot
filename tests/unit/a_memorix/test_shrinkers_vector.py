"""ZG-27 测试：CachedMapShrinker count/scan（测试组 6——真实对象测试）。"""

import pytest

from src.A_memorix.core.runtime.shrinker import ShrinkControl
from src.A_memorix.core.runtime.shrinkers.cached_map import CachedMapShrinker


class _FakeVectorStore:
    def __init__(self):
        self._cached_map = {"a": 1, "b": 2}


@pytest.mark.asyncio
async def test_cached_map_count_and_scan():
    vs = _FakeVectorStore()
    shrinker = CachedMapShrinker(vs)
    sc = ShrinkControl()
    assert await shrinker.count_objects(sc) == 1
    freed = await shrinker.scan_objects(sc)
    assert freed == 1
    assert len(vs._cached_map) == 0


@pytest.mark.asyncio
async def test_cached_map_count_zero_when_empty():
    vs = _FakeVectorStore()
    vs._cached_map = {}
    shrinker = CachedMapShrinker(vs)
    sc = ShrinkControl()
    assert await shrinker.count_objects(sc) == 0