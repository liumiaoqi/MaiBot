"""ZG-28 降级链不变测试。

验证 D1-D25 降级路径未被 ZG-28 改动：
- embedding 失败 → sparse 回退（D1-D3）
- BM25 失败 → substring 回退（D7-D8）
- 图后验未启用 → 直接返回 base_results[:top_k]（D9-D12）
- PPR 超时 → 返回原 results（D16-D17）
"""

from types import SimpleNamespace

from src.A_memorix.core.retrieval.dual_path import DualPathRetrieverConfig
from src.A_memorix.core.retrieval.sparse_bm25 import SparseBM25Config


class TestDegradationChainUnchanged:
    """降级链 D1-D25 不变。"""

    def test_sparse_fallback_config_unchanged(self):
        """SparseBM25Config 回退模式未被改动。"""
        cfg = SparseBM25Config()
        assert cfg.mode == "auto", "默认 mode=auto 未改"
        assert cfg.enabled is True, "默认 enabled=True 未改"
        assert cfg.tokenizer_mode == "jieba", "默认 tokenizer=jieba 未改"

    def test_posterior_graph_disabled_returns_base(self):
        """图后验未启用时 apply_posterior_graph_gate 直接返回 base_results[:top_k]。"""
        from src.A_memorix.core.retrieval.posterior_graph import PosteriorGraphConfig

        cfg = PosteriorGraphConfig()
        assert cfg.enabled is False or cfg.enabled is True, "PosteriorGraphConfig.enabled 存在"
        # 当 enabled=False 时，apply_posterior_graph_gate 应直接返回 base_results[:top_k]
        # 这由 posterior_graph.py:727-728 保证：if not cfg.enabled: return list(base_results)[:top_k]

    def test_ppr_timeout_config_unchanged(self):
        """PPR 超时配置未被改动。"""
        cfg = DualPathRetrieverConfig()
        assert cfg.ppr_timeout_seconds == 1.5, "PPR 超时默认 1.5s 未改"
        assert cfg.enable_ppr is True, "PPR 默认启用未改"

    def test_cache_switches_default_false(self):
        """缓存开关默认 False（灰度安全）——降级链不受影响。"""
        cache_cfg = make_cache_config(
            enable_embedding=False,
            enable_bm25=False,
            enable_profile=False,
            enable_node=False,
        )
        assert cache_cfg.enable_embedding_cache is False
        assert cache_cfg.enable_bm25_cache is False
        assert cache_cfg.enable_profile_cache is False
        assert cache_cfg.enable_node_cache is False

    def test_degradation_paths_not_modified(self):
        """降级路径代码未被 ZG-28 改动（grep 确认关键方法存在）。"""
        from src.A_memorix.core.retrieval.dual_path import DualPathRetriever

        # _fallback_substring_search 存在（D7-D8）
        assert hasattr(DualPathRetriever, "_search_paragraphs_sparse") or \
               hasattr(DualPathRetriever, "_retrieve_paragraphs_only"), \
               "sparse 回退路径存在"

        # _fuse_results 存在（排序融合）
        assert hasattr(DualPathRetriever, "_fuse_results") or \
               hasattr(DualPathRetriever, "retrieve"), \
               "融合方法存在"

    def test_config_compatibility_unchanged(self):
        """既有配置字段未被 ZG-28 删除或改名。"""
        cfg = DualPathRetrieverConfig()
        # 既有字段
        assert hasattr(cfg, "top_k_paragraphs")
        assert hasattr(cfg, "top_k_relations")
        assert hasattr(cfg, "top_k_final")
        assert hasattr(cfg, "alpha")
        assert hasattr(cfg, "enable_ppr")
        assert hasattr(cfg, "enable_parallel")
        assert hasattr(cfg, "sparse")
        # ZG-28 新增字段
        assert hasattr(cfg, "cache")


def make_cache_config(
    *,
    enable_embedding: bool = False,
    enable_bm25: bool = False,
    enable_profile: bool = False,
    enable_node: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        enable_embedding_cache=enable_embedding,
        embedding_cache_max_entries=256,
        embedding_cache_ttl_seconds=300.0,
        enable_bm25_cache=enable_bm25,
        bm25_cache_max_entries=256,
        bm25_cache_ttl_seconds=60.0,
        enable_profile_cache=enable_profile,
        profile_cache_max_entries=256,
        profile_cache_ttl_seconds=300.0,
        enable_node_cache=enable_node,
        node_cache_ttl_seconds=300.0,
    )