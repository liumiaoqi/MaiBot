"""ZG-28 节点缓存命中测试。

验证 NodeCache 命中时跳过 get_nodes() + 节点变更时 invalidate()。
"""

import time

from src.A_memorix.core.retrieval.caches.node_cache import NodeCache
from tests.unit.a_memorix._zg28_helpers import FakeGraphStore


class TestNodeCacheHit:
    """节点缓存命中行为。"""

    def test_cache_hit_skips_get_nodes(self):
        """图未变更时重复调用 get_nodes() 次数降为 1。"""
        cache = NodeCache(ttl_seconds=300.0)
        graph = FakeGraphStore(nodes=["实体A", "实体B", "实体C"])
        get_nodes_calls = 0

        for _ in range(10):
            cached = cache.get()
            if cached is None:
                nodes = graph.get_nodes()
                get_nodes_calls += 1
                cache.put(nodes)
            # 命中时不调 get_nodes

        assert get_nodes_calls == 1, "10 次调用只拉 1 次 get_nodes"
        assert graph.get_nodes_calls == 1

    def test_invalidate_on_node_change(self):
        """graph_store.add_node 后 invalidate() → 下次重新拉。"""
        cache = NodeCache(ttl_seconds=300.0)
        graph = FakeGraphStore(nodes=["实体A"])
        get_nodes_calls = 0

        # 首次拉取
        cached = cache.get()
        if cached is None:
            nodes = graph.get_nodes()
            get_nodes_calls += 1
            cache.put(nodes)

        # 节点变更 → invalidate
        graph.add_nodes(["实体B"])
        cache.invalidate()

        # 再次拉取 → 重新走 get_nodes
        cached = cache.get()
        if cached is None:
            nodes = graph.get_nodes()
            get_nodes_calls += 1
            cache.put(nodes)

        assert get_nodes_calls == 2, "invalidate 后重新拉"
        assert "实体B" in nodes, "新节点应可见"

    def test_invalidate_on_delete(self):
        """graph_store.delete_node 后 invalidate() → 下次重新拉。"""
        cache = NodeCache(ttl_seconds=300.0)
        graph = FakeGraphStore(nodes=["实体A", "实体B"])

        # 首次拉取
        cached = cache.get()
        if cached is None:
            nodes = graph.get_nodes()
            cache.put(nodes)

        # 删除节点 → invalidate
        graph.delete_nodes(["实体A"])
        cache.invalidate()

        # 再次拉取
        cached = cache.get()
        assert cached is None, "invalidate 后缓存清空"
        nodes = graph.get_nodes()
        assert "实体A" not in nodes, "删除的节点不应出现"

    def test_ttl_expiry_forces_reload(self):
        """TTL 过期后重新拉。"""
        cache = NodeCache(ttl_seconds=0.05)
        cache.put(["节点1", "节点2"])
        assert cache.get() is not None

        time.sleep(0.06)
        assert cache.get() is None, "TTL 过期后未命中"

    def test_single_entry_overwrite(self):
        """单例缓存：put 2 次覆盖旧缓存。"""
        cache = NodeCache(ttl_seconds=300.0)
        cache.put(["旧节点"])
        cache.put(["新节点"])
        result = cache.get()
        assert result == ["新节点"], "后 put 覆盖前 put"