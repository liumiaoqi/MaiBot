"""ZG-28 P0-2 性能基准测试。

验证 P0-2 批量替换后 SQL 次数从 24 降为 1。
"""

from pathlib import Path

import pytest

from src.A_memorix.core.retrieval.posterior_graph import _linked_core_paragraph_hashes
from tests.unit.a_memorix._zg28_helpers import make_metadata_store, seed_relations_and_paragraphs


class TestBenchmarkP02:
    """P0-2 性能基准。"""

    @pytest.fixture
    def store_and_retriever(self, tmp_path: Path):
        store = make_metadata_store(tmp_path)
        entities = [f"Entity{i}" for i in range(12)]
        relations = [(entities[i], "rel", entities[i + 1]) for i in range(11)]
        paragraphs = [(f"Entity{i} rel Entity{i+1}", "test") for i in range(11)]
        seed = seed_relations_and_paragraphs(store, entities=entities, relations=relations, paragraphs=paragraphs)

        class _MinimalRetriever:
            def __init__(self, ms):
                self.metadata_store = ms

        retriever = _MinimalRetriever(store)
        yield store, retriever, seed
        store.close()

    def test_sql_count_batch_vs_individual(self, store_and_retriever):
        """批量 SQL 次数=1 vs 逐条 SQL 次数=24。"""
        store, retriever, seed = store_and_retriever
        relation_hashes = seed["relation_hashes"]

        # 批量：1 次 SQL
        store.get_paragraph_hashes_by_relation_hashes(relation_hashes)
        batch_sql = 1

        # 逐条：N 次 SQL（N = len(relation_hashes)）
        individual_sql = 0
        for rh in relation_hashes:
            _linked_core_paragraph_hashes(retriever, rh)
            individual_sql += 1

        assert batch_sql == 1, "批量 1 次 SQL"
        assert individual_sql == len(relation_hashes), f"逐条 {len(relation_hashes)} 次 SQL"
        assert individual_sql / batch_sql == len(relation_hashes), f"SQL 降 {len(relation_hashes)}x"

    def test_results_consistent(self, store_and_retriever):
        """批量与逐条结果一致。"""
        store, retriever, seed = store_and_retriever
        relation_hashes = seed["relation_hashes"]

        batch = store.get_paragraph_hashes_by_relation_hashes(relation_hashes)

        for rh in relation_hashes:
            individual = set(_linked_core_paragraph_hashes(retriever, rh))
            batch_hashes = set(batch.get(rh, []))
            assert batch_hashes == individual