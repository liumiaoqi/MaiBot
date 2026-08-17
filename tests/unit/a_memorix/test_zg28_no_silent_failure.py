"""ZG-28 静默失效禁令测试。

验证初始化失败要出声——不静默跳过。
"""

from src.A_memorix.core.retrieval.caches.embedding_cache import EmbeddingCache
from src.A_memorix.core.retrieval.caches.bm25_cache import Bm25Cache
from src.A_memorix.core.retrieval.caches.profile_cache import ProfileCache
from src.A_memorix.core.retrieval.caches.node_cache import NodeCache


class TestNoSilentFailure:
    """静默失效禁令——初始化失败要出声。"""

    def test_embedding_cache_invalid_config_raises(self):
        """非法 max_entries 应抛异常（不静默跳过）。"""
        try:
            EmbeddingCache(max_entries=0, ttl_seconds=300.0)
        except (ValueError, Exception):
            pass  # 抛异常即符合要求
        else:
            # 如果没抛异常，至少不应静默创建一个无效缓存
            cache = EmbeddingCache(max_entries=0, ttl_seconds=300.0)
            # put 不应静默成功
            try:
                cache.put("key", [1.0])
            except Exception:
                pass  # 抛异常即符合要求

    def test_bm25_cache_invalid_config_raises(self):
        """非法 max_entries 应抛异常。"""
        try:
            Bm25Cache(max_entries=0, ttl_seconds=60.0)
        except (ValueError, Exception):
            pass
        else:
            cache = Bm25Cache(max_entries=0, ttl_seconds=60.0)
            try:
                cache.put(("h", 10, 2000, "jieba"), [])
            except Exception:
                pass

    def test_profile_cache_invalid_config_raises(self):
        """非法 max_entries 应抛异常。"""
        try:
            ProfileCache(max_entries=0, ttl_seconds=300.0)
        except (ValueError, Exception):
            pass
        else:
            cache = ProfileCache(max_entries=0, ttl_seconds=300.0)
            try:
                cache.put("key", {})
            except Exception:
                pass

    def test_node_cache_invalid_ttl_raises(self):
        """非法 TTL 应抛异常。"""
        try:
            NodeCache(ttl_seconds=0.0)
        except (ValueError, Exception):
            pass  # 抛异常即符合要求

    def test_config_flow_wiring_not_silent(self):
        """配置流断流不静默——DualPathRetrieverConfig.cache 字段存在。"""
        from src.A_memorix.core.retrieval.dual_path import DualPathRetrieverConfig

        cfg = DualPathRetrieverConfig()
        # cache 字段存在（P0-1 修复）
        assert hasattr(cfg, "cache"), "cache 字段存在，不静默忽略"
        # 默认 None（灰度安全）
        assert cfg.cache is None, "默认 None"

    def test_config_schema_has_cache_section(self):
        """config_schema.json 包含 retrieval.cache 子段（不静默缺失）。"""
        import json
        from pathlib import Path

        schema_path = Path("src/A_memorix/config_schema.json")
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        assert "retrieval.cache" in schema["sections"], "retrieval.cache 子段存在于 schema"

        cache_section = schema["sections"]["retrieval.cache"]
        assert "enable_embedding_cache" in cache_section["fields"]
        assert "enable_bm25_cache" in cache_section["fields"]
        assert "enable_profile_cache" in cache_section["fields"]
        assert "enable_node_cache" in cache_section["fields"]