"""ZG-28 shrinker 注册测试。

验证 3 个新缓存类 shrinker 注册到 ReclaimScheduler。
"""

from src.A_memorix.core.retrieval.caches.embedding_cache import EmbeddingCache
from src.A_memorix.core.retrieval.caches.bm25_cache import Bm25Cache
from src.A_memorix.core.retrieval.caches.profile_cache import ProfileCache
from src.A_memorix.core.runtime.shrinkers.embedding_cache_shrinker import EmbeddingCacheShrinker
from src.A_memorix.core.runtime.shrinkers.bm25_cache_shrinker import Bm25CacheShrinker
from src.A_memorix.core.runtime.shrinkers.profile_cache_shrinker import ProfileCacheShrinker


class TestShrinkerRegistration:
    """3 个新 shrinker 注册到 ReclaimScheduler。"""

    def test_embedding_cache_shrinker_construct(self):
        """EmbeddingCacheShrinker 可构造 + seeks=1。"""
        cache = EmbeddingCache(max_entries=10, ttl_seconds=300.0)
        shrinker = EmbeddingCacheShrinker(cache)
        assert shrinker.seeks == 1, "纯缓存最优先驱逐"
        assert shrinker.name == "embedding_cache"

    def test_bm25_cache_shrinker_construct(self):
        """Bm25CacheShrinker 可构造 + seeks=1。"""
        cache = Bm25Cache(max_entries=10, ttl_seconds=60.0)
        shrinker = Bm25CacheShrinker(cache)
        assert shrinker.seeks == 1
        assert shrinker.name == "bm25_cache"

    def test_profile_cache_shrinker_construct(self):
        """ProfileCacheShrinker 可构造 + seeks=1。"""
        cache = ProfileCache(max_entries=10, ttl_seconds=300.0)
        shrinker = ProfileCacheShrinker(cache)
        assert shrinker.seeks == 1
        assert shrinker.name == "profile_cache"

    def test_shrinker_all_seeks_equal_one(self):
        """3 个 shrinker seeks=1（纯缓存，可重建，最优先驱逐）。"""
        emb_s = EmbeddingCacheShrinker(EmbeddingCache())
        bm25_s = Bm25CacheShrinker(Bm25Cache())
        prof_s = ProfileCacheShrinker(ProfileCache())

        assert emb_s.seeks == 1
        assert bm25_s.seeks == 1
        assert prof_s.seeks == 1

    def test_shrinker_registration_in_initializer(self):
        """grep 确认 3 个 shrinker 在 kernel_initializer.py 注册。"""
        from pathlib import Path

        init_path = Path("src/A_memorix/core/runtime/services/kernel_initializer.py")
        content = init_path.read_text(encoding="utf-8")
        assert "EmbeddingCacheShrinker" in content, "EmbeddingCacheShrinker 已注册"
        assert "Bm25CacheShrinker" in content, "Bm25CacheShrinker 已注册"
        assert "ProfileCacheShrinker" in content, "ProfileCacheShrinker 已注册"
        assert "reclaim_scheduler.register" in content, "reclaim_scheduler.register 调用存在"

    def test_node_cache_no_shrinker(self):
        """节点缓存单例不注册 shrinker（容量 1，TTL + 失效订阅足够）。"""
        from pathlib import Path

        init_path = Path("src/A_memorix/core/runtime/services/kernel_initializer.py")
        content = init_path.read_text(encoding="utf-8")
        assert "NodeCacheShrinker" not in content, "节点缓存不应有 shrinker"
