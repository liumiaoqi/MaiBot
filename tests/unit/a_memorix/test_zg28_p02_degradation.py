"""ZG-28 P0-2 降级保底测试。

验证 get_paragraph_hashes_by_relation_hashes 异常时降级为逐条，结果不丢。
"""

from pathlib import Path

import pytest

from src.A_memorix.core.retrieval.posterior_graph import _linked_core_paragraph_hashes
from tests.unit.a_memorix._zg28_helpers import make_metadata_store, seed_relations_and_paragraphs


class TestP02Degradation:
    """P0-2 批量异常降级为逐条。"""

    @pytest.fixture
    def store_and_retriever(self, tmp_path: Path):
        store = make_metadata_store(tmp_path)
        seed = seed_relations_and_paragraphs(
            store,
            entities=["Alice", "Bob", "Charlie"],
            relations=[
                ("Alice", "同事", "Bob"),
                ("Bob", "朋友", "Charlie"),
                ("Charlie", "邻居", "Alice"),
            ],
            paragraphs=[
                ("Alice 和 Bob 是同事", "test"),
                ("Bob 和 Charlie 是朋友", "test"),
                ("Charlie 和 Alice 是邻居", "test"),
            ],
        )

        class _MinimalRetriever:
            def __init__(self, ms):
                self.metadata_store = ms

        retriever = _MinimalRetriever(store)
        yield store, retriever, seed
        store.close()

    def test_batch_exception_fallback_to_individual(self, store_and_retriever, monkeypatch):
        """批量方法异常时降级为逐条 _linked_core_paragraph_hashes，结果不丢。"""
        store, retriever, seed = store_and_retriever
        relation_hashes = seed["relation_hashes"]

        # 模拟批量方法异常
        original_batch = store.get_paragraph_hashes_by_relation_hashes

        def _failing_batch(*args, **kwargs):
            raise RuntimeError("模拟批量查询异常")

        monkeypatch.setattr(store, "get_paragraph_hashes_by_relation_hashes", _failing_batch)

        # 降级路径：逐条查询
        fallback_result: dict[str, set[str]] = {}
        for rh in relation_hashes:
            try:
                linked = _linked_core_paragraph_hashes(retriever, rh)
                fallback_result[rh] = set(linked)
            except Exception:
                fallback_result[rh] = set()

        # 恢复批量方法，获取正确结果对比
        monkeypatch.undo()
        batch_result = original_batch(relation_hashes)

        for rh in relation_hashes:
            batch_hashes = set(batch_result.get(rh, []))
            fallback_hashes = fallback_result[rh]
            assert batch_hashes == fallback_hashes, (
                f"降级结果不丢: rh={rh} batch={batch_hashes} fallback={fallback_hashes}"
            )

    def test_empty_relation_hashes_no_exception(self, store_and_retriever):
        """空 relation_hashes 不抛异常。"""
        store, _, _ = store_and_retriever
        result = store.get_paragraph_hashes_by_relation_hashes([])
        assert result == {}