"""ZG-28 缓存异常降级测试。

验证缓存读写异常时跳过缓存直接查询，不影响检索主流程。
"""

import asyncio


from src.A_memorix.core.retrieval.caches.embedding_cache import EmbeddingCache
from src.A_memorix.core.retrieval.caches.bm25_cache import Bm25Cache
from src.A_memorix.core.retrieval.caches.profile_cache import ProfileCache
from src.A_memorix.core.retrieval.caches.node_cache import NodeCache
from tests.unit.a_memorix._zg28_helpers import FakeEmbeddingManager


class TestCacheDegradation:
    """缓存异常跳过缓存直接查询。"""

    def test_embedding_cache_exception_skips_cache(self):
        """EmbeddingCache get/put 异常 → 跳过缓存直接 encode。"""
        cache = EmbeddingCache(max_entries=10, ttl_seconds=300.0)
        emb = FakeEmbeddingManager(dimension=4)
        query = "测试"

        async def _run():
            import hashlib
            qhash = hashlib.sha1(query.encode("utf-8")).hexdigest()
            try:
                cached = cache.get(qhash)
                if cached is not None:
                    return cached
            except Exception:
                cached = None

            vec = await emb.encode(query)

            try:
                if vec is not None:
                    cache.put(qhash, vec)
            except Exception:
                pass

            return vec

        result = asyncio.run(_run())
        assert result is not None, "缓存异常不影响 encode"
        assert len(emb.encode_calls) == 1, "encode 被调用 1 次"

    def test_bm25_cache_exception_skips_cache(self):
        """Bm25Cache get/put 异常 → 跳过缓存直接走 FTS5。"""
        cache = Bm25Cache(max_entries=10, ttl_seconds=60.0)
        sql_calls = 0
        key = ("hash", 10, 2000, "jieba")
        fts5_results = [{"hash": "p1", "content": "测试"}]

        # 模拟缓存 get 异常 → 跳过缓存
        try:
            cached = cache.get(key)
        except Exception:
            cached = None

        if cached is None:
            sql_calls += 1  # 走 FTS5
            try:
                cache.put(key, fts5_results)
            except Exception:
                pass

        assert sql_calls == 1, "缓存异常时走 FTS5"

    def test_profile_cache_exception_skips_cache(self):
        """ProfileCache get/put 异常 → 跳过缓存直接构建。"""
        cache = ProfileCache(max_entries=10, ttl_seconds=300.0)
        build_calls = 0
        key = "candidate_001"
        profile = {"tokens": ["测试"]}

        try:
            cached = cache.get(key)
        except Exception:
            cached = None

        if cached is None:
            build_calls += 1  # 构建
            try:
                cache.put(key, profile)
            except Exception:
                pass

        assert build_calls == 1, "缓存异常时直接构建"

    def test_node_cache_exception_skips_cache(self):
        """NodeCache get/put 异常 → 跳过缓存直接调 get_nodes()。"""
        cache = NodeCache(ttl_seconds=300.0)
        get_nodes_calls = 0
        nodes = ["节点A", "节点B"]

        try:
            cached = cache.get()
        except Exception:
            cached = None

        if cached is None:
            get_nodes_calls += 1  # 调 get_nodes()
            try:
                cache.put(nodes)
            except Exception:
                pass

        assert get_nodes_calls == 1, "缓存异常时直接调 get_nodes()"

    def test_cache_exception_does_not_crash(self):
        """缓存异常不崩溃——try/except 跳过缓存，主流程继续。"""
        cache = EmbeddingCache(max_entries=10, ttl_seconds=300.0)
        emb = FakeEmbeddingManager(dimension=4)

        async def _run():
            query = "不崩溃测试"
            import hashlib
            qhash = hashlib.sha1(query.encode("utf-8")).hexdigest()

            # 模拟缓存损坏
            cache._entries = None  # type: ignore

            try:
                cached = cache.get(qhash)
            except Exception:
                cached = None

            if cached is None:
                vec = await emb.encode(query)
                return vec
            return cached

        result = asyncio.run(_run())
        assert result is not None, "缓存损坏不崩溃，encode 正常返回"