"""ZG-27 测试：PprCacheShrinker count/scan（测试组 6——真实 tuple 结构测试）。

真实 _ppr_cache 条目结构（dual_path.py:346,2437-2440）：
    Tuple[float, Dict[str, float]]
    entry[0] = time.monotonic() + ttl_seconds  （过期时间戳）
    entry[1] = dict(scores)
"""

import time

import pytest

from src.A_memorix.core.runtime.shrinker import ShrinkControl
from src.A_memorix.core.runtime.shrinkers.ppr import PprCacheShrinker


class _FakeDualPath:
    """模拟 DualPathRetriever，_ppr_cache 使用真实 tuple 结构。"""

    def __init__(self, cache=None):
        self._ppr_cache = cache if cache is not None else {}


def _make_entry(expires_at: float, scores=None):
    """构造真实结构条目 Tuple[float, Dict]。"""
    return (expires_at, scores or {"score": 1.0})


@pytest.mark.asyncio
async def test_ppr_count_expired():
    """count_objects 返回超 TTL 条数（真实 tuple 结构）。"""
    now = time.monotonic()
    cache = {
        "a": _make_entry(now - 10),
        "b": _make_entry(now + 100),
        "c": _make_entry(now - 5),
    }
    retriever = _FakeDualPath(cache)
    shrinker = PprCacheShrinker(retriever)
    sc = ShrinkControl()
    count = await shrinker.count_objects(sc)
    assert count == 2


@pytest.mark.asyncio
async def test_ppr_scan_evicts_expired():
    """scan_objects pop 过期条目（真实 tuple 结构）。"""
    now = time.monotonic()
    cache = {
        "a": _make_entry(now - 10),
        "b": _make_entry(now + 100),
    }
    retriever = _FakeDualPath(cache)
    shrinker = PprCacheShrinker(retriever)
    sc = ShrinkControl()
    freed = await shrinker.scan_objects(sc)
    assert freed == 1
    assert "a" not in cache
    assert "b" in cache


@pytest.mark.asyncio
async def test_ppr_count_zero_when_no_expired():
    """无过期 → count 返回 0。"""
    now = time.monotonic()
    cache = {"a": _make_entry(now + 100)}
    retriever = _FakeDualPath(cache)
    shrinker = PprCacheShrinker(retriever)
    sc = ShrinkControl()
    count = await shrinker.count_objects(sc)
    assert count == 0
