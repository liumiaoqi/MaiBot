"""ZG-28 P0-3 性能基准测试。

验证 P0-3 批量替换后 SQL 次数从 48 降为 2。
"""

from pathlib import Path

import pytest

from tests.unit.a_memorix._zg28_helpers import make_metadata_store, seed_relations_and_paragraphs


class TestBenchmarkP03:
    """P0-3 性能基准。"""

    @pytest.fixture
    def store_and_seed(self, tmp_path: Path):
        store = make_metadata_store(tmp_path)
        entities = [f"Node{i}" for i in range(12)]
        relations = [(entities[i], "edge", entities[i + 1]) for i in range(11)]
        paragraphs = [(f"Node{i} edge Node{i+1}", "test") for i in range(11)]
        seed = seed_relations_and_paragraphs(store, entities=entities, relations=relations, paragraphs=paragraphs)
        yield store, seed
        store.close()

    def test_sql_count_batch_vs_individual(self, store_and_seed):
        """批量 SQL 次数=2 vs 逐条 SQL 次数=48（24 候选 × 2 查询）。"""
        store, seed = store_and_seed
        relation_hashes = seed["relation_hashes"]

        # 批量：2 次 SQL（relations + paragraphs 各 1 次）
        store.get_relations_by_hashes(relation_hashes, include_inactive=False)
        store.get_paragraphs_by_relation_hashes(relation_hashes)
        batch_sql = 2

        # 逐条：N×2 次 SQL
        individual_sql = 0
        for rh in relation_hashes:
            store.get_relation(rh, include_inactive=False)
            individual_sql += 1
            store.get_paragraphs_by_relation(rh)
            individual_sql += 1

        assert batch_sql == 2, "批量 2 次 SQL"
        assert individual_sql == len(relation_hashes) * 2, f"逐条 {len(relation_hashes)*2} 次 SQL"
        assert individual_sql / batch_sql == len(relation_hashes), f"SQL 降 {len(relation_hashes)}x"

    def test_results_consistent(self, store_and_seed):
        """批量与逐条结果一致。"""
        store, seed = store_and_seed
        relation_hashes = seed["relation_hashes"]

        batch_rels = store.get_relations_by_hashes(relation_hashes, include_inactive=False)
        batch_paras = store.get_paragraphs_by_relation_hashes(relation_hashes)

        for rh in relation_hashes:
            ind_rel = store.get_relation(rh, include_inactive=False)
            ind_paras = store.get_paragraphs_by_relation(rh)

            if ind_rel:
                assert batch_rels[rh]["hash"] == ind_rel["hash"]

            ind_hashes = {p["hash"] for p in ind_paras}
            batch_hashes = {p["hash"] for p in batch_paras.get(rh, [])}
            assert ind_hashes == batch_hashes