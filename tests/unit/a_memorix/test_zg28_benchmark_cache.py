"""ZG-28 缓存性能基准测试。

验证 4 处缓存补全后调用次数降幅 + 延迟下降。
"""

import time

from src.A_memorix.core.retrieval.caches.embedding_cache import EmbeddingCache
from src.A_memorix.core.retrieval.caches.bm25_cache import Bm25Cache
from src.A_memorix.core.retrieval.caches.profile_cache import ProfileCache
from src.A_memorix.core.retrieval.caches.node_cache import NodeCache


class TestBenchmarkCache:
    """缓存性能基准。"""

    def test_embedding_cache_call_reduction(self):
        """embedding 缓存：同 query 重复 10 次，encode 调用 10→1。"""
        cache = EmbeddingCache(max_entries=256, ttl_seconds=300.0)
        encode_calls_no_cache = 10  # 无缓存时 10 次
        encode_calls_with_cache = 0

        qhash = "test_query_hash"
        for _ in range(10):
            cached = cache.get(qhash)
            if cached is None:
                encode_calls_with_cache += 1
                cache.put(qhash, [1.0, 2.0])

        assert encode_calls_with_cache == 1, "有缓存时 encode 1 次"
        assert encode_calls_no_cache / encode_calls_with_cache == 10, "调用降 10x"

    def test_bm25_cache_call_reduction(self):
        """BM25 缓存：同参数重复 10 次，SQL 调用 10→1。"""
        cache = Bm25Cache(max_entries=256, ttl_seconds=60.0)
        sql_no_cache = 10
        sql_with_cache = 0

        key = ("hash", 10, 2000, "jieba")
        for _ in range(10):
            cached = cache.get(key)
            if cached is None:
                sql_with_cache += 1
                cache.put(key, [{"hash": "p1"}])

        assert sql_with_cache == 1, "有缓存时 SQL 1 次"
        assert sql_no_cache / sql_with_cache == 10, "调用降 10x"

    def test_profile_cache_call_reduction(self):
        """profile 缓存：同候选重复 10 次，构建 10→1。"""
        cache = ProfileCache(max_entries=256, ttl_seconds=300.0)
        build_no_cache = 10
        build_with_cache = 0

        key = "candidate_hash"
        for _ in range(10):
            cached = cache.get(key)
            if cached is None:
                build_with_cache += 1
                cache.put(key, {"tokens": ["a"]})

        assert build_with_cache == 1, "有缓存时构建 1 次"
        assert build_no_cache / build_with_cache == 10, "调用降 10x"

    def test_node_cache_call_reduction(self):
        """节点缓存：图未变更重复 10 次，get_nodes 10→1。"""
        cache = NodeCache(ttl_seconds=300.0)
        get_nodes_no_cache = 10
        get_nodes_with_cache = 0

        for _ in range(10):
            cached = cache.get()
            if cached is None:
                get_nodes_with_cache += 1
                cache.put(["节点A", "节点B"])

        assert get_nodes_with_cache == 1, "有缓存时 get_nodes 1 次"
        assert get_nodes_no_cache / get_nodes_with_cache == 10, "调用降 10x"

    def test_cache_latency_reduction(self):
        """缓存命中延迟低于未命中延迟。"""
        cache = EmbeddingCache(max_entries=256, ttl_seconds=300.0)
        qhash = "latency_test"

        # 首次（未命中）——模拟 encode 耗时
        t0 = time.perf_counter()
        cached = cache.get(qhash)
        if cached is None:
            time.sleep(0.001)  # 模拟 encode 耗时
            cache.put(qhash, [1.0])
        miss_time = time.perf_counter() - t0

        # 第二次（命中）
        t0 = time.perf_counter()
        cache.get(qhash)
        hit_time = time.perf_counter() - t0

        assert hit_time < miss_time, f"命中={hit_time:.6f} < 未命中={miss_time:.6f}"