"""ZG-28 缓存容量上限 + TTL 生效 + LRU 淘汰测试。

测试各缓存类的容量上限、TTL 过期、LRU 淘汰行为。
"""

import time


from src.A_memorix.core.retrieval.caches.embedding_cache import EmbeddingCache
from src.A_memorix.core.retrieval.caches.bm25_cache import Bm25Cache
from src.A_memorix.core.retrieval.caches.profile_cache import ProfileCache
from src.A_memorix.core.retrieval.caches.node_cache import NodeCache


class TestEmbeddingCacheEviction:
    """EmbeddingCache 容量上限 + TTL + LRU 淘汰。"""

    def test_capacity_limit_evicts_oldest(self):
        cache = EmbeddingCache(max_entries=3, ttl_seconds=300.0)
        cache.put("a", [1.0])
        cache.put("b", [2.0])
        cache.put("c", [3.0])
        assert cache.size == 3
        cache.put("d", [4.0])
        assert cache.size == 3, "容量超限时应 LRU 淘汰 1 条"

    def test_ttl_expiry(self):
        cache = EmbeddingCache(max_entries=10, ttl_seconds=0.05)
        cache.put("a", [1.0])
        assert cache.get("a") is not None
        time.sleep(0.06)
        assert cache.get("a") is None, "TTL 过期后应返回 None"

    def test_get_returns_cached_value(self):
        cache = EmbeddingCache(max_entries=10, ttl_seconds=300.0)
        cache.put("a", [1.0, 2.0])
        result = cache.get("a")
        assert result == [1.0, 2.0]

    def test_get_miss_returns_none(self):
        cache = EmbeddingCache(max_entries=10, ttl_seconds=300.0)
        assert cache.get("nonexistent") is None


class TestBm25CacheEviction:
    """Bm25Cache 容量上限 + TTL + LRU 淘汰 + clear()。"""

    def test_capacity_limit_evicts_oldest(self):
        cache = Bm25Cache(max_entries=3, ttl_seconds=60.0)
        for i in range(3):
            cache.put((f"q{i}", 10, 200, "jieba"), [{"hash": f"h{i}"}])
        assert cache.size == 3
        cache.put(("q3", 10, 200, "jieba"), [{"hash": "h3"}])
        assert cache.size == 3

    def test_ttl_expiry(self):
        cache = Bm25Cache(max_entries=10, ttl_seconds=0.05)
        cache.put(("q", 10, 200, "jieba"), [{"hash": "h"}])
        assert cache.get(("q", 10, 200, "jieba")) is not None
        time.sleep(0.06)
        assert cache.get(("q", 10, 200, "jieba")) is None

    def test_clear_empties_cache(self):
        cache = Bm25Cache(max_entries=10, ttl_seconds=60.0)
        cache.put(("q1", 10, 200, "jieba"), [{"hash": "h1"}])
        cache.put(("q2", 10, 200, "jieba"), [{"hash": "h2"}])
        assert cache.size == 2
        cache.clear()
        assert cache.size == 0

    def test_get_returns_cached_value(self):
        cache = Bm25Cache(max_entries=10, ttl_seconds=60.0)
        results = [{"hash": "h1", "score": 1.0}]
        cache.put(("q", 10, 200, "jieba"), results)
        assert cache.get(("q", 10, 200, "jieba")) == results


class TestProfileCacheEviction:
    """ProfileCache 容量上限 + TTL + LRU 淘汰。"""

    def test_capacity_limit_evicts_oldest(self):
        cache = ProfileCache(max_entries=3, ttl_seconds=300.0)
        for i in range(3):
            cache.put(f"key{i}", {"tokens": {f"t{i}"}})
        assert cache.size == 3
        cache.put("key3", {"tokens": {"t3"}})
        assert cache.size == 3

    def test_ttl_expiry(self):
        cache = ProfileCache(max_entries=10, ttl_seconds=0.05)
        cache.put("key", {"tokens": {"t1"}})
        assert cache.get("key") is not None
        time.sleep(0.06)
        assert cache.get("key") is None

    def test_get_returns_cached_value(self):
        cache = ProfileCache(max_entries=10, ttl_seconds=300.0)
        profile = {"text": "hello", "tokens": {"hello", "world"}}
        cache.put("key", profile)
        assert cache.get("key") == profile


class TestNodeCacheEviction:
    """NodeCache 单例容量 1 + TTL + invalidate()。"""

    def test_single_entry_overwrites_old(self):
        cache = NodeCache(ttl_seconds=300.0)
        cache.put(["node_a", "node_b"])
        assert cache.get() == ["node_a", "node_b"]
        cache.put(["node_c"])
        assert cache.get() == ["node_c"], "单例缓存 put 应覆盖旧值"

    def test_ttl_expiry(self):
        cache = NodeCache(ttl_seconds=0.05)
        cache.put(["node_a"])
        assert cache.get() is not None
        time.sleep(0.06)
        assert cache.get() is None

    def test_invalidate_clears_cache(self):
        cache = NodeCache(ttl_seconds=300.0)
        cache.put(["node_a", "node_b"])
        assert cache.get() is not None
        cache.invalidate()
        assert cache.get() is None, "invalidate 后应返回 None"

    def test_get_miss_returns_none(self):
        cache = NodeCache(ttl_seconds=300.0)
        assert cache.get() is None