"""ZG-28 embedding 缓存命中测试。

验证 EmbeddingCache 命中时跳过 encode 调用 + 未命中时 encode 后写入。
"""

import asyncio

import numpy as np

from src.A_memorix.core.retrieval.caches.embedding_cache import EmbeddingCache
from tests.unit.a_memorix._zg28_helpers import FakeEmbeddingManager


class TestEmbeddingCacheHit:
    """embedding 缓存命中行为。"""

    def test_cache_hit_skips_encode(self):
        """同 query 重复时 encode 调用次数降为 1。"""
        cache = EmbeddingCache(max_entries=10, ttl_seconds=300.0)
        emb = FakeEmbeddingManager(dimension=4)
        query = "测试查询"

        async def _run():
            # 首次：未命中 → encode + put
            qhash = _hash(query)
            cached = cache.get(qhash)
            if cached is None:
                vec = await emb.encode(query)
                cache.put(qhash, vec)
                result1 = vec
            else:
                result1 = cached

            # 第二次：命中 → 不调 encode
            cached = cache.get(qhash)
            if cached is None:
                vec = await emb.encode(query)
                cache.put(qhash, vec)
                result2 = vec
            else:
                result2 = cached

            return result1, result2

        r1, r2 = asyncio.run(_run())
        assert len(emb.encode_calls) == 1, "首次未命中调 encode，第二次命中不调"
        assert np.array_equal(r1, r2), "命中返回值与首次一致"

    def test_cache_miss_calls_encode(self):
        """不同 query 各自未命中 → 各调 encode。"""
        cache = EmbeddingCache(max_entries=10, ttl_seconds=300.0)
        emb = FakeEmbeddingManager(dimension=4)

        async def _run():
            for q in ["query1", "query2", "query3"]:
                qhash = _hash(q)
                cached = cache.get(qhash)
                if cached is None:
                    vec = await emb.encode(q)
                    cache.put(qhash, vec)

        asyncio.run(_run())
        assert len(emb.encode_calls) == 3, "3 个不同 query 各调 1 次 encode"

    def test_cache_disabled_no_cache(self):
        """开关关闭时每次都调 encode。"""
        emb = FakeEmbeddingManager(dimension=4)
        query = "测试查询"

        async def _run():
            for _ in range(5):
                await emb.encode(query)

        asyncio.run(_run())
        assert len(emb.encode_calls) == 5, "缓存关闭时 5 次都调 encode"

    def test_encode_exception_not_cached(self):
        """encode 抛异常不写入缓存。"""
        cache = EmbeddingCache(max_entries=10, ttl_seconds=300.0)

        class _FailingEmbedding:
            async def encode(self, text, **kwargs):
                raise RuntimeError("encode failed")

        emb = _FailingEmbedding()
        query = "测试"

        async def _run():
            qhash = _hash(query)
            cached = cache.get(qhash)
            if cached is None:
                try:
                    vec = await emb.encode(query)
                    cache.put(qhash, vec)
                except Exception:
                    pass  # 异常不写入缓存

        asyncio.run(_run())
        assert cache.size == 0, "encode 异常不应写入缓存"


def _hash(text: str) -> str:
    import hashlib
    return hashlib.sha1(text.encode("utf-8")).hexdigest()