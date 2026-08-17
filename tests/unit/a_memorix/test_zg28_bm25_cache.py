"""ZG-28 BM25 缓存命中测试。

验证 Bm25Cache 命中时跳过 FTS5 SQL + 索引变更时 clear()。
"""

from src.A_memorix.core.retrieval.caches.bm25_cache import Bm25Cache


class TestBm25CacheHit:
    """BM25 缓存命中行为。"""

    def test_cache_hit_skips_sql(self):
        """同查询参数重复时 SQL 调用次数降为 1。"""
        cache = Bm25Cache(max_entries=10, ttl_seconds=60.0)
        sql_calls = 0
        key = ("query_hash_1", 10, 2000, "jieba")
        results = [{"hash": "p1", "content": "测试", "score": 0.9}]

        # 首次：未命中 → 走 SQL + put
        cached = cache.get(key)
        if cached is None:
            sql_calls += 1
            cache.put(key, results)
            r1 = results
        else:
            r1 = cached

        # 第二次：命中 → 不走 SQL
        cached = cache.get(key)
        if cached is None:
            sql_calls += 1
            cache.put(key, results)
            r2 = results
        else:
            r2 = cached

        assert sql_calls == 1, "首次走 SQL，第二次命中不走"
        assert r1 == r2, "命中返回值一致"

    def test_clear_on_index_change(self):
        """add_paragraph 后 clear() → 下次重新走 SQL。"""
        cache = Bm25Cache(max_entries=10, ttl_seconds=60.0)
        sql_calls = 0
        key = ("query_hash_1", 10, 2000, "jieba")
        results = [{"hash": "p1", "content": "测试", "score": 0.9}]

        # 首次查询
        cached = cache.get(key)
        if cached is None:
            sql_calls += 1
            cache.put(key, results)

        # 索引变更 → clear
        cache.clear()
        assert cache.size == 0, "clear 后缓存清空"

        # 再次查询 → 重新走 SQL
        cached = cache.get(key)
        if cached is None:
            sql_calls += 1
            cache.put(key, results)

        assert sql_calls == 2, "clear 后重新走 SQL"

    def test_different_params_no_hit(self):
        """不同查询参数（limit/max_doc_len/tokenizer）不命中。"""
        cache = Bm25Cache(max_entries=10, ttl_seconds=60.0)
        key1 = ("hash", 10, 2000, "jieba")
        key2 = ("hash", 20, 2000, "jieba")
        key3 = ("hash", 10, 2000, "char_2gram")

        cache.put(key1, [{"hash": "p1"}])
        assert cache.get(key1) is not None
        assert cache.get(key2) is None, "不同 limit 不命中"
        assert cache.get(key3) is None, "不同 tokenizer 不命中"

    def test_ttl_expiry_forces_sql(self):
        """TTL 过期后重新走 SQL。"""
        import time
        cache = Bm25Cache(max_entries=10, ttl_seconds=0.05)
        key = ("hash", 10, 2000, "jieba")
        cache.put(key, [{"hash": "p1"}])
        assert cache.get(key) is not None

        time.sleep(0.06)
        assert cache.get(key) is None, "TTL 过期后未命中"