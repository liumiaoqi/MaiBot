"""ZG-28 Bm25CacheShrinker 测试。

count=超 TTL 条数，scan=pop 过期，seeks=1。
"""

import asyncio
import time


from src.A_memorix.core.retrieval.caches.bm25_cache import Bm25Cache
from src.A_memorix.core.runtime.shrinker import ShrinkControl
from src.A_memorix.core.runtime.shrinkers.bm25_cache_shrinker import Bm25CacheShrinker


class TestBm25CacheShrinker:
    """Bm25CacheShrinker count/scan 行为。"""

    def test_name_and_seeks(self):
        assert Bm25CacheShrinker.name == "bm25_cache"
        assert Bm25CacheShrinker.seeks == 1

    def test_count_zero_on_empty_cache(self):
        cache = Bm25Cache(max_entries=10, ttl_seconds=60.0)
        shrinker = Bm25CacheShrinker(cache)
        sc = ShrinkControl()
        count = asyncio.run(shrinker.count_objects(sc))
        assert count == 0

    def test_count_expired_entries(self):
        cache = Bm25Cache(max_entries=10, ttl_seconds=0.05)
        cache.put(("q1", 10, 200, "jieba"), [{"hash": "h1"}])
        cache.put(("q2", 10, 200, "jieba"), [{"hash": "h2"}])
        time.sleep(0.06)
        shrinker = Bm25CacheShrinker(cache)
        sc = ShrinkControl()
        count = asyncio.run(shrinker.count_objects(sc))
        assert count == 2

    def test_scan_pops_expired_entries(self):
        cache = Bm25Cache(max_entries=10, ttl_seconds=0.05)
        cache.put(("q1", 10, 200, "jieba"), [{"hash": "h1"}])
        cache.put(("q2", 10, 200, "jieba"), [{"hash": "h2"}])
        time.sleep(0.06)
        shrinker = Bm25CacheShrinker(cache)
        sc = ShrinkControl()
        freed = asyncio.run(shrinker.scan_objects(sc))
        assert freed == 2
        assert cache.size == 0

    def test_scan_preserves_fresh_entries(self):
        cache = Bm25Cache(max_entries=10, ttl_seconds=60.0)
        cache.put(("q1", 10, 200, "jieba"), [{"hash": "h1"}])
        shrinker = Bm25CacheShrinker(cache)
        sc = ShrinkControl()
        freed = asyncio.run(shrinker.scan_objects(sc))
        assert freed == 0
        assert cache.size == 1