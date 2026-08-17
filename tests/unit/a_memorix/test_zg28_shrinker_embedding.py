"""ZG-28 EmbeddingCacheShrinker 测试。

count=超 TTL 条数，scan=pop 过期，seeks=1。
"""

import asyncio
import time


from src.A_memorix.core.retrieval.caches.embedding_cache import EmbeddingCache
from src.A_memorix.core.runtime.shrinker import ShrinkControl
from src.A_memorix.core.runtime.shrinkers.embedding_cache_shrinker import EmbeddingCacheShrinker


class TestEmbeddingCacheShrinker:
    """EmbeddingCacheShrinker count/scan 行为。"""

    def test_name_and_seeks(self):
        assert EmbeddingCacheShrinker.name == "embedding_cache"
        assert EmbeddingCacheShrinker.seeks == 1

    def test_count_zero_on_empty_cache(self):
        cache = EmbeddingCache(max_entries=10, ttl_seconds=60.0)
        shrinker = EmbeddingCacheShrinker(cache)
        sc = ShrinkControl()
        count = asyncio.run(shrinker.count_objects(sc))
        assert count == 0

    def test_count_zero_on_fresh_entries(self):
        cache = EmbeddingCache(max_entries=10, ttl_seconds=60.0)
        cache.put("a", [1.0])
        cache.put("b", [2.0])
        shrinker = EmbeddingCacheShrinker(cache)
        sc = ShrinkControl()
        count = asyncio.run(shrinker.count_objects(sc))
        assert count == 0, "未过期条目不应计入 count"

    def test_count_expired_entries(self):
        cache = EmbeddingCache(max_entries=10, ttl_seconds=0.05)
        cache.put("a", [1.0])
        cache.put("b", [2.0])
        time.sleep(0.06)
        shrinker = EmbeddingCacheShrinker(cache)
        sc = ShrinkControl()
        count = asyncio.run(shrinker.count_objects(sc))
        assert count == 2, "2 条过期条目应计入 count"

    def test_scan_pops_expired_entries(self):
        cache = EmbeddingCache(max_entries=10, ttl_seconds=0.05)
        cache.put("a", [1.0])
        cache.put("b", [2.0])
        cache.put("c", [3.0])
        time.sleep(0.06)
        shrinker = EmbeddingCacheShrinker(cache)
        sc = ShrinkControl()
        freed = asyncio.run(shrinker.scan_objects(sc))
        assert freed == 3, "应释放 3 条过期条目"
        assert cache.size == 0

    def test_scan_preserves_fresh_entries(self):
        cache = EmbeddingCache(max_entries=10, ttl_seconds=60.0)
        cache.put("fresh", [1.0])
        shrinker = EmbeddingCacheShrinker(cache)
        sc = ShrinkControl()
        freed = asyncio.run(shrinker.scan_objects(sc))
        assert freed == 0
        assert cache.size == 1, "未过期条目不应被释放"