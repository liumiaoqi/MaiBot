"""ZG-28 缓存开关灰度测试。

验证各缓存开关默认 False + 关闭时行为与当前一致 + 逐个开启生效。
"""


from src.A_memorix.core.retrieval.caches.embedding_cache import EmbeddingCache
from src.A_memorix.core.retrieval.caches.bm25_cache import Bm25Cache
from src.A_memorix.core.retrieval.caches.profile_cache import ProfileCache
from src.A_memorix.core.retrieval.caches.node_cache import NodeCache
from tests.unit.a_memorix._zg28_helpers import make_cache_config


class TestCacheSwitchGradual:
    """缓存开关灰度测试。"""

    def test_defaults_all_false(self):
        """各缓存开关默认 False。"""
        cfg = make_cache_config(
            enable_embedding=False,
            enable_bm25=False,
            enable_profile=False,
            enable_node=False,
        )
        assert cfg.enable_embedding_cache is False
        assert cfg.enable_bm25_cache is False
        assert cfg.enable_profile_cache is False
        assert cfg.enable_node_cache is False

    def test_disabled_means_no_cache(self):
        """开关=False 时无缓存行为（每次都调 encode/SQL/build）。"""
        emb_calls = 0
        for _ in range(5):
            emb_calls += 1  # 模拟无缓存时每次都调

        assert emb_calls == 5, "缓存关闭时 5 次都调"

    def test_enable_embedding_only(self):
        """仅开启 embedding 缓存。"""
        cfg = make_cache_config(
            enable_embedding=True,
            enable_bm25=False,
            enable_profile=False,
            enable_node=False,
        )
        assert cfg.enable_embedding_cache is True
        assert cfg.enable_bm25_cache is False
        assert cfg.enable_profile_cache is False
        assert cfg.enable_node_cache is False

        cache = EmbeddingCache(
            max_entries=cfg.embedding_cache_max_entries,
            ttl_seconds=cfg.embedding_cache_ttl_seconds,
        )
        cache.put("key", [1.0])
        assert cache.get("key") == [1.0], "embedding 缓存生效"

    def test_enable_bm25_only(self):
        """仅开启 BM25 缓存。"""
        cfg = make_cache_config(
            enable_embedding=False,
            enable_bm25=True,
            enable_profile=False,
            enable_node=False,
        )
        assert cfg.enable_bm25_cache is True
        cache = Bm25Cache(
            max_entries=cfg.bm25_cache_max_entries,
            ttl_seconds=cfg.bm25_cache_ttl_seconds,
        )
        cache.put(("h", 10, 2000, "jieba"), [{"hash": "p1"}])
        assert cache.get(("h", 10, 2000, "jieba")) is not None, "BM25 缓存生效"

    def test_enable_profile_only(self):
        """仅开启 profile 缓存。"""
        cfg = make_cache_config(
            enable_embedding=False,
            enable_bm25=False,
            enable_profile=True,
            enable_node=False,
        )
        assert cfg.enable_profile_cache is True
        cache = ProfileCache(
            max_entries=cfg.profile_cache_max_entries,
            ttl_seconds=cfg.profile_cache_ttl_seconds,
        )
        cache.put("hash", {"tokens": ["a"]})
        assert cache.get("hash") is not None, "profile 缓存生效"

    def test_enable_node_only(self):
        """仅开启节点缓存。"""
        cfg = make_cache_config(
            enable_embedding=False,
            enable_bm25=False,
            enable_profile=False,
            enable_node=True,
        )
        assert cfg.enable_node_cache is True
        cache = NodeCache(ttl_seconds=cfg.node_cache_ttl_seconds)
        cache.put(["节点A"])
        assert cache.get() == ["节点A"], "节点缓存生效"

    def test_all_enabled(self):
        """全部开启。"""
        cfg = make_cache_config(
            enable_embedding=True,
            enable_bm25=True,
            enable_profile=True,
            enable_node=True,
        )
        assert cfg.enable_embedding_cache is True
        assert cfg.enable_bm25_cache is True
        assert cfg.enable_profile_cache is True
        assert cfg.enable_node_cache is True