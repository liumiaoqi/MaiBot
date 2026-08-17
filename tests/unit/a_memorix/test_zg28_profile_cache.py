"""ZG-28 profile 缓存命中测试。

验证 ProfileCache 命中时跳过 jieba 分词 + gate 内复用。
"""

from src.A_memorix.core.retrieval.caches.profile_cache import ProfileCache


class TestProfileCacheHit:
    """profile 缓存命中行为。"""

    def test_cache_hit_skips_build(self):
        """同候选重复构建 profile 时构建次数降为 1。"""
        cache = ProfileCache(max_entries=10, ttl_seconds=300.0)
        build_calls = 0
        candidate_hash = "candidate_001"
        profile = {"tokens": ["测试", "候选"], "entities": ["实体1"]}

        # 首次：未命中 → 构建 + put
        cached = cache.get(candidate_hash)
        if cached is None:
            build_calls += 1
            cache.put(candidate_hash, profile)
            r1 = profile
        else:
            r1 = cached

        # 第二次：命中 → 不构建
        cached = cache.get(candidate_hash)
        if cached is None:
            build_calls += 1
            cache.put(candidate_hash, profile)
            r2 = profile
        else:
            r2 = cached

        assert build_calls == 1, "首次构建，第二次命中不构建"
        assert r1 == r2, "命中返回值一致"

    def test_gate_internal_reuse(self):
        """同一 hash_value 在一次 gate 内只构建一次 profile。"""
        cache = ProfileCache(max_entries=10, ttl_seconds=300.0)
        build_calls = 0
        hash_value = "para_hash_123"
        profile = {"tokens": ["文本"], "entities": []}

        # 模拟 gate 内多次引用同一候选
        for _ in range(10):
            cached = cache.get(hash_value)
            if cached is None:
                build_calls += 1
                cache.put(hash_value, profile)

        assert build_calls == 1, "gate 内 10 次引用只构建 1 次"

    def test_different_candidates_no_hit(self):
        """不同候选 hash 不命中。"""
        cache = ProfileCache(max_entries=10, ttl_seconds=300.0)
        cache.put("hash_a", {"tokens": ["a"]})
        assert cache.get("hash_a") is not None
        assert cache.get("hash_b") is None, "不同候选不命中"

    def test_query_profile_cache(self):
        """query profile 缓存（键=query 哈希）。"""
        cache = ProfileCache(max_entries=10, ttl_seconds=300.0)
        import hashlib
        query_hash = hashlib.sha1("测试查询".encode("utf-8")).hexdigest()
        profile = {"tokens": ["测试", "查询"], "intent": "relation"}

        cache.put(query_hash, profile)
        assert cache.get(query_hash) == profile
        assert cache.get("different_hash") is None