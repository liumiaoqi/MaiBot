"""ZG-27 测试：SaliencyCacheShrinker + AdjacencyTShrinker（测试组 6——真实对象测试）。"""

import pytest

from src.A_memorix.core.runtime.shrinker import ShrinkControl
from src.A_memorix.core.runtime.shrinkers.adjacency_t import AdjacencyTShrinker
from src.A_memorix.core.runtime.shrinkers.saliency import SaliencyCacheShrinker


class _FakeGraphStore:
    def __init__(self):
        self._saliency_cache = {"data": 1}
        self._adjacency_T = {"matrix": 1}
        self._adjacency_dirty = False


@pytest.mark.asyncio
async def test_saliency_count_and_scan():
    gs = _FakeGraphStore()
    shrinker = SaliencyCacheShrinker(gs)
    sc = ShrinkControl()
    assert await shrinker.count_objects(sc) == 1
    freed = await shrinker.scan_objects(sc)
    assert freed == 1
    assert gs._saliency_cache is None


@pytest.mark.asyncio
async def test_saliency_count_zero_when_none():
    gs = _FakeGraphStore()
    gs._saliency_cache = None
    shrinker = SaliencyCacheShrinker(gs)
    sc = ShrinkControl()
    assert await shrinker.count_objects(sc) == 0


@pytest.mark.asyncio
async def test_adjacency_count_and_scan():
    gs = _FakeGraphStore()
    shrinker = AdjacencyTShrinker(gs)
    sc = ShrinkControl()
    assert await shrinker.count_objects(sc) == 1
    freed = await shrinker.scan_objects(sc)
    assert freed == 1
    assert gs._adjacency_T is None
    assert gs._adjacency_dirty is True


@pytest.mark.asyncio
async def test_adjacency_count_zero_when_none():
    gs = _FakeGraphStore()
    gs._adjacency_T = None
    shrinker = AdjacencyTShrinker(gs)
    sc = ShrinkControl()
    assert await shrinker.count_objects(sc) == 0