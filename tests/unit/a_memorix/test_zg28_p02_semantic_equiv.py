"""ZG-28 P0-2 语义等价测试：批量 vs 逐条关联段落查询一致。

验证 get_paragraph_hashes_by_relation_hashes 批量查询结果与逐条
_linked_core_paragraph_hashes 调用结果完全一致。
"""

from pathlib import Path

import pytest

from src.A_memorix.core.retrieval.posterior_graph import _linked_core_paragraph_hashes
from tests.unit.a_memorix._zg28_helpers import make_metadata_store, seed_relations_and_paragraphs


class TestP02SemanticEquiv:
    """P0-2 批量 vs 逐条语义等价。"""

    @pytest.fixture
    def store_and_retriever(self, tmp_path: Path):
        """构造真实 SQLite MetadataStore + 最小 DualPathRetriever mock。"""
        store = make_metadata_store(tmp_path)
        seed = seed_relations_and_paragraphs(
            store,
            entities=["Alice", "Bob", "Charlie", "Diana"],
            relations=[
                ("Alice", "同事", "Bob"),
                ("Alice", "朋友", "Charlie"),
                ("Bob", "邻居", "Diana"),
                ("Charlie", "同学", "Alice"),
            ],
            paragraphs=[
                ("Alice 和 Bob 是同事关系", "test"),
                ("Alice 和 Charlie 是朋友", "test"),
                ("Bob 和 Diana 是邻居", "test"),
                ("Charlie 和 Alice 是同学", "test"),
            ],
        )

        # 构造最小 retriever mock（_linked_core_paragraph_hashes 需要 retriever.metadata_store）
        class _MinimalRetriever:
            def __init__(self, ms):
                self.metadata_store = ms

        retriever = _MinimalRetriever(store)
        yield store, retriever, seed
        store.close()

    def test_batch_equals_individual(self, store_and_retriever):
        """批量 get_paragraph_hashes_by_relation_hashes 与逐条 _linked_core_paragraph_hashes 一致。"""
        store, retriever, seed = store_and_retriever
        relation_hashes = seed["relation_hashes"]

        # 批量路径
        batch_result = store.get_paragraph_hashes_by_relation_hashes(relation_hashes)

        # 逐条路径
        individual_result: dict[str, set[str]] = {}
        for rh in relation_hashes:
            linked = _linked_core_paragraph_hashes(retriever, rh)
            individual_result[rh] = set(linked)

        # 断言每个 relation_hash 的 paragraph hash 集合一致
        for rh in relation_hashes:
            batch_hashes = set(batch_result.get(rh, []))
            individual_hashes = individual_result[rh]
            assert batch_hashes == individual_hashes, (
                f"relation_hash={rh}: batch={batch_hashes} != individual={individual_hashes}"
            )

    def test_batch_empty_input(self, store_and_retriever):
        """空 relation_hashes 返回空 dict。"""
        store, _, _ = store_and_retriever
        result = store.get_paragraph_hashes_by_relation_hashes([])
        assert result == {}

    def test_batch_single_relation(self, store_and_retriever):
        """单个 relation_hash 批量与逐条一致。"""
        store, retriever, seed = store_and_retriever
        rh = seed["relation_hashes"][0]

        batch = store.get_paragraph_hashes_by_relation_hashes([rh])
        individual = set(_linked_core_paragraph_hashes(retriever, rh))

        assert set(batch.get(rh, [])) == individual

    def test_batch_nonexistent_relation(self, store_and_retriever):
        """不存在的 relation_hash 返回空列表。"""
        store, _, _ = store_and_retriever
        result = store.get_paragraph_hashes_by_relation_hashes(["nonexistent_hash"])
        assert result.get("nonexistent_hash", []) == []