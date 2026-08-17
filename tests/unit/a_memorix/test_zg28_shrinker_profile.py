"""ZG-28 ProfileCacheShrinker 测试。

count=超 TTL 条数，scan=pop 过期，seeks=1。
"""

import asyncio
import time


from src.A_memorix.core.retrieval.caches.profile_cache import ProfileCache
from src.A_memorix.core.runtime.shrinker import ShrinkControl
from src.A_memorix.core.runtime.shrinkers.profile_cache_shrinker import ProfileCacheShrinker


class TestProfileCacheShrinker:
    """ProfileCacheShrinker count/scan 行为。"""

    def test_name_and_seeks(self):
        assert ProfileCacheShrinker.name == "profile_cache"
        assert ProfileCacheShrinker.seeks == 1

    def test_count_zero_on_empty_cache(self):
        cache = ProfileCache(max_entries=10, ttl_seconds=60.0)
        shrinker = ProfileCacheShrinker(cache)
        sc = ShrinkControl()
        count = asyncio.run(shrinker.count_objects(sc))
        assert count == 0

    def test_count_expired_entries(self):
        cache = ProfileCache(max_entries=10, ttl_seconds=0.05)
        cache.put("key1", {"tokens": {"t1"}})
        cache.put("key2", {"tokens": {"t2"}})
        time.sleep(0.06)
        shrinker = ProfileCacheShrinker(cache)
        sc = ShrinkControl()
        count = asyncio.run(shrinker.count_objects(sc))
        assert count == 2

    def test_scan_pops_expired_entries(self):
        cache = ProfileCache(max_entries=10, ttl_seconds=0.05)
        cache.put("key1", {"tokens": {"t1"}})
        cache.put("key2", {"tokens": {"t2"}})
        time.sleep(0.06)
        shrinker = ProfileCacheShrinker(cache)
        sc = ShrinkControl()
        freed = asyncio.run(shrinker.scan_objects(sc))
        assert freed == 2
        assert cache.size == 0

    def test_scan_preserves_fresh_entries(self):
        cache = ProfileCache(max_entries=10, ttl_seconds=60.0)
        cache.put("key1", {"tokens": {"t1"}})
        shrinker = ProfileCacheShrinker(cache)
        sc = ShrinkControl()
        freed = asyncio.run(shrinker.scan_objects(sc))
        assert freed == 0
        assert cache.size == 1