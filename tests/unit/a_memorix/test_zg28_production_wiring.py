"""ZG-28 生产路径接线测试（AGENTS.md 硬性规则——新模块必须存在生产接线点）。

验证所有新增/改动模块在生产路径中存在调用点，禁止"只有定义没有调用点"。
用 grep + import 验证生产调用点存在——只有测试里调用不算接线。
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _grep(pattern: str, file_path: str) -> list[str]:
    """在源码中 grep 查找模式，返回命中行列表。"""
    full_path = REPO_ROOT / file_path
    if not full_path.exists():
        return []
    content = full_path.read_text(encoding="utf-8")
    return [f"{i+1}: {line}" for i, line in enumerate(content.splitlines()) if pattern in line]


class TestBatchApiProductionCallSites:
    """组18.1: 验证新增批量 API 存在生产调用点。"""

    def test_p01_batch_api_called_in_dual_path(self):
        hits = _grep("get_relations_by_entity_names", "src/A_memorix/core/retrieval/dual_path.py")
        assert len(hits) > 0, "P0-1 批量 API get_relations_by_entity_names 未在 dual_path.py 中调用"

    def test_p02_batch_api_called_in_posterior_graph(self):
        hits = _grep("get_paragraph_hashes_by_relation_hashes", "src/A_memorix/core/retrieval/posterior_graph.py")
        assert len(hits) > 0, "P0-2 批量 API get_paragraph_hashes_by_relation_hashes 未在 posterior_graph.py 中调用"

    def test_p03_batch_api_called_in_graph_relation_recall(self):
        hits_rel = _grep("get_relations_by_hashes", "src/A_memorix/core/retrieval/graph_relation_recall.py")
        hits_para = _grep("get_paragraphs_by_relation_hashes", "src/A_memorix/core/retrieval/graph_relation_recall.py")
        assert len(hits_rel) > 0, "P0-3 get_relations_by_hashes 未在 graph_relation_recall.py 中调用"
        assert len(hits_para) > 0, "P0-3 get_paragraphs_by_relation_hashes 未在 graph_relation_recall.py 中调用"

    def test_batch_api_defined_in_relation_store(self):
        hits = _grep("def get_relations_by_entity_names", "src/A_memorix/core/storage/stores/relation_store.py")
        assert len(hits) > 0, "get_relations_by_entity_names 未在 relation_store.py 中定义"

    def test_batch_api_forwarded_in_metadata_store(self):
        hits = _grep("get_relations_by_entity_names", "src/A_memorix/core/storage/metadata_store.py")
        assert len(hits) > 0, "get_relations_by_entity_names 未在 metadata_store.py 中转发"


class TestCacheMountPoints:
    """组18.2: 验证 4 处缓存挂载点存在。"""

    def test_embedding_cache_mounted_in_dual_path(self):
        hits = _grep("_embedding_cache", "src/A_memorix/core/retrieval/dual_path.py")
        assert len(hits) >= 3, "embedding 缓存未在 dual_path.py 中挂载（至少 3 处：init + get + put）"

    def test_bm25_cache_mounted_in_sparse_bm25(self):
        hits = _grep("_bm25_cache", "src/A_memorix/core/retrieval/sparse_bm25.py")
        assert len(hits) >= 3, "BM25 缓存未在 sparse_bm25.py 中挂载"

    def test_profile_cache_mounted_in_posterior_graph(self):
        hits = _grep("_profile_cache", "src/A_memorix/core/retrieval/posterior_graph.py")
        assert len(hits) >= 2, "profile 缓存未在 posterior_graph.py 中挂载"

    def test_profile_cache_held_in_dual_path(self):
        hits = _grep("_profile_cache", "src/A_memorix/core/retrieval/dual_path.py")
        assert len(hits) >= 2, "profile 缓存实例未在 dual_path.py 中持有"

    def test_node_cache_mounted_in_dual_path(self):
        hits = _grep("_node_cache", "src/A_memorix/core/retrieval/dual_path.py")
        assert len(hits) >= 3, "节点缓存未在 dual_path.py 中挂载"


class TestShrinkerRegistrationInKernelInitializer:
    """组18.3: 验证 3 个新 shrinker 注册到 ReclaimScheduler。"""

    def test_embedding_cache_shrinker_registered(self):
        hits = _grep("EmbeddingCacheShrinker", "src/A_memorix/core/runtime/services/kernel_initializer.py")
        assert len(hits) >= 2, "EmbeddingCacheShrinker 未在 kernel_initializer.py 中注册（import + register）"

    def test_bm25_cache_shrinker_registered(self):
        hits = _grep("Bm25CacheShrinker", "src/A_memorix/core/runtime/services/kernel_initializer.py")
        assert len(hits) >= 2, "Bm25CacheShrinker 未在 kernel_initializer.py 中注册"

    def test_profile_cache_shrinker_registered(self):
        hits = _grep("ProfileCacheShrinker", "src/A_memorix/core/runtime/services/kernel_initializer.py")
        assert len(hits) >= 2, "ProfileCacheShrinker 未在 kernel_initializer.py 中注册"

    def test_reclaim_scheduler_register_called(self):
        hits = _grep("reclaim_scheduler.register", "src/A_memorix/core/runtime/services/kernel_initializer.py")
        assert len(hits) >= 7, "reclaim_scheduler.register 调用不足（应有 7+ 个：4 既有 + 3 新）"


class TestNodeCacheInvalidationSubscription:
    """组18.4: 验证节点缓存失效订阅接线。"""

    def test_invalidate_callback_defined(self):
        hits = _grep("_invalidate_node_cache", "src/A_memorix/core/retrieval/dual_path.py")
        assert len(hits) >= 2, "_invalidate_node_cache 未在 dual_path.py 中定义和注册"

    def test_graph_store_has_callback_registration(self):
        hits = _grep("register_node_change_callback", "src/A_memorix/core/storage/graph_store.py")
        assert len(hits) >= 1, "register_node_change_callback 未在 graph_store.py 中定义"

    def test_graph_store_notifies_on_add_nodes(self):
        hits = _grep("_notify_node_change", "src/A_memorix/core/storage/graph_store.py")
        assert len(hits) >= 3, "_notify_node_change 未在 graph_store.py 中调用（定义 + add_nodes + delete_nodes）"


class TestConfigCacheSubsection:
    """组18.5: 验证配置 retrieval.cache 子段存在。"""

    def test_embedding_cache_config_exists(self):
        hits = _grep("enable_embedding_cache", "src/config/official_configs.py")
        assert len(hits) >= 1, "enable_embedding_cache 未在 official_configs.py 中定义"

    def test_bm25_cache_config_exists(self):
        hits = _grep("enable_bm25_cache", "src/config/official_configs.py")
        assert len(hits) >= 1, "enable_bm25_cache 未在 official_configs.py 中定义"

    def test_profile_cache_config_exists(self):
        hits = _grep("enable_profile_cache", "src/config/official_configs.py")
        assert len(hits) >= 1, "enable_profile_cache 未在 official_configs.py 中定义"

    def test_node_cache_config_exists(self):
        hits = _grep("enable_node_cache", "src/config/official_configs.py")
        assert len(hits) >= 1, "enable_node_cache 未在 official_configs.py 中定义"

    def test_cache_config_class_exists(self):
        hits = _grep("class AMemorixRetrievalCacheConfig", "src/config/official_configs.py")
        assert len(hits) >= 1, "AMemorixRetrievalCacheConfig 类未定义"


class TestCacheClassesExist:
    """验证 4 个缓存类文件存在且可导入。"""

    def test_embedding_cache_importable(self):
        from src.A_memorix.core.retrieval.caches.embedding_cache import EmbeddingCache
        cache = EmbeddingCache(max_entries=10, ttl_seconds=60.0)
        assert cache is not None

    def test_bm25_cache_importable(self):
        from src.A_memorix.core.retrieval.caches.bm25_cache import Bm25Cache
        cache = Bm25Cache(max_entries=10, ttl_seconds=60.0)
        assert cache is not None

    def test_profile_cache_importable(self):
        from src.A_memorix.core.retrieval.caches.profile_cache import ProfileCache
        cache = ProfileCache(max_entries=10, ttl_seconds=60.0)
        assert cache is not None

    def test_node_cache_importable(self):
        from src.A_memorix.core.retrieval.caches.node_cache import NodeCache
        cache = NodeCache(ttl_seconds=60.0)
        assert cache is not None


class TestShrinkerClassesExist:
    """验证 3 个 shrinker 类文件存在且可导入。"""

    def test_embedding_cache_shrinker_importable(self):
        from src.A_memorix.core.runtime.shrinkers.embedding_cache_shrinker import EmbeddingCacheShrinker
        assert EmbeddingCacheShrinker.name == "embedding_cache"
        assert EmbeddingCacheShrinker.seeks == 1

    def test_bm25_cache_shrinker_importable(self):
        from src.A_memorix.core.runtime.shrinkers.bm25_cache_shrinker import Bm25CacheShrinker
        assert Bm25CacheShrinker.name == "bm25_cache"
        assert Bm25CacheShrinker.seeks == 1

    def test_profile_cache_shrinker_importable(self):
        from src.A_memorix.core.runtime.shrinkers.profile_cache_shrinker import ProfileCacheShrinker
        assert ProfileCacheShrinker.name == "profile_cache"
        assert ProfileCacheShrinker.seeks == 1


class TestConfigFlowWiring:
    """P0-1 修复验证: 配置流真实构造链测试（测得出配置断流）。"""

    def test_dual_path_config_has_cache_field(self):
        """DualPathRetrieverConfig 必须有 cache 字段。"""
        from src.A_memorix.core.retrieval.dual_path import DualPathRetrieverConfig
        from dataclasses import fields
        field_names = {f.name for f in fields(DualPathRetrieverConfig)}
        assert "cache" in field_names, "DualPathRetrieverConfig 缺少 cache 字段"

    def test_config_cache_dict_to_namespace(self):
        """cache 字段 dict 输入应自动转为 SimpleNamespace（支持 getattr）。"""
        from src.A_memorix.core.retrieval.dual_path import DualPathRetrieverConfig
        from types import SimpleNamespace
        config = DualPathRetrieverConfig(cache={"enable_embedding_cache": True})
        assert isinstance(config.cache, SimpleNamespace), "cache dict 应转为 SimpleNamespace"
        assert config.cache.enable_embedding_cache is True

    def test_search_runtime_initializer_passes_cache(self):
        """search_runtime_initializer.py 必须传递 cache 参数。"""
        hits = _grep("retrieval.cache", "src/A_memorix/core/runtime/search_runtime_initializer.py")
        assert len(hits) > 0, "search_runtime_initializer.py 未传递 retrieval.cache 配置"

    def test_person_profile_service_passes_cache(self):
        """person_profile_service.py 必须传递 cache 参数。"""
        hits = _grep("retrieval.cache", "src/A_memorix/core/utils/person_profile_service.py")
        assert len(hits) > 0, "person_profile_service.py 未传递 retrieval.cache 配置"

    def test_no_report_warning_usage(self):
        """P0-2 修复: 不应使用不存在的 report_warning API。"""
        for f in [
            "src/A_memorix/core/retrieval/dual_path.py",
            "src/A_memorix/core/retrieval/posterior_graph.py",
            "src/A_memorix/core/retrieval/graph_relation_recall.py",
        ]:
            hits = _grep("report_warning", f)
            assert len(hits) == 0, f"{f} 仍使用不存在的 report_warning API"

    def test_error_escalation_uses_port_report(self):
        """P0-2 修复: 应使用 port.report(ErrorLevel.WARNING, ...)。"""
        for f in [
            "src/A_memorix/core/retrieval/dual_path.py",
            "src/A_memorix/core/retrieval/posterior_graph.py",
            "src/A_memorix/core/retrieval/graph_relation_recall.py",
        ]:
            hits = _grep("port.report(ErrorLevel.WARNING", f)
            assert len(hits) > 0, f"{f} 未使用 port.report(ErrorLevel.WARNING, ...)"