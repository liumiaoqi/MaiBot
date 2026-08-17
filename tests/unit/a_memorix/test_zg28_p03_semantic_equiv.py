"""ZG-28 P0-3 语义等价测试：批量 vs 逐条图关系召回一致。

验证 get_relations_by_hashes + get_paragraphs_by_relation_hashes
批量查询结果与逐条 get_relation + get_paragraphs_by_relation 一致。
"""

from pathlib import Path

import pytest

from tests.unit.a_memorix._zg28_helpers import make_metadata_store, seed_relations_and_paragraphs


class TestP03SemanticEquiv:
    """P0-3 批量 vs 逐条语义等价。"""

    @pytest.fixture
    def store_and_seed(self, tmp_path: Path):
        store = make_metadata_store(tmp_path)
        seed = seed_relations_and_paragraphs(
            store,
            entities=["Python", "Rust", "Go", "Java"],
            relations=[
                ("Python", "similar_to", "Rust"),
                ("Python", "different_from", "Go"),
                ("Rust", "compiles_to", "Java"),
                ("Go", "concurrent_with", "Java"),
            ],
            paragraphs=[
                ("Python 和 Rust 有相似之处", "test"),
                ("Python 和 Go 有所不同", "test"),
                ("Rust 可以编译到 Java", "test"),
                ("Go 与 Java 并发对比", "test"),
            ],
        )
        yield store, seed
        store.close()

    def test_batch_relations_equal_individual(self, store_and_seed):
        """批量 get_relations_by_hashes 与逐条 get_relation 一致。"""
        store, seed = store_and_seed
        relation_hashes = seed["relation_hashes"]

        # 批量
        batch = store.get_relations_by_hashes(relation_hashes, include_inactive=False)

        # 逐条
        for rh in relation_hashes:
            individual = store.get_relation(rh, include_inactive=False)
            batch_rel = batch.get(rh)
            if individual is None:
                assert batch_rel is None, f"relation={rh}: batch should be None"
            else:
                assert batch_rel is not None, f"relation={rh}: batch should not be None"
                assert batch_rel["hash"] == individual["hash"]
                assert batch_rel["subject"] == individual["subject"]
                assert batch_rel["predicate"] == individual["predicate"]
                assert batch_rel["object"] == individual["object"]

    def test_batch_paragraphs_equal_individual(self, store_and_seed):
        """批量 get_paragraphs_by_relation_hashes 与逐条 get_paragraphs_by_relation 一致。"""
        store, seed = store_and_seed
        relation_hashes = seed["relation_hashes"]

        # 批量
        batch = store.get_paragraphs_by_relation_hashes(relation_hashes)

        # 逐条
        for rh in relation_hashes:
            individual = store.get_paragraphs_by_relation(rh)
            batch_paras = batch.get(rh, [])

            individual_hashes = {p["hash"] for p in individual}
            batch_hashes = {p["hash"] for p in batch_paras}
            assert individual_hashes == batch_hashes, (
                f"relation={rh}: individual={individual_hashes} != batch={batch_hashes}"
            )

    def test_batch_combined_equal_individual(self, store_and_seed):
        """批量组合（relations + paragraphs）与逐条组合一致。"""
        store, seed = store_and_seed
        relation_hashes = seed["relation_hashes"]

        # 批量
        batch_rels = store.get_relations_by_hashes(relation_hashes, include_inactive=False)
        batch_paras = store.get_paragraphs_by_relation_hashes(relation_hashes)

        # 逐条
        for rh in relation_hashes:
            ind_rel = store.get_relation(rh, include_inactive=False)
            ind_paras = store.get_paragraphs_by_relation(rh)

            # relation 一致
            batch_rel = batch_rels.get(rh)
            if ind_rel is None:
                assert batch_rel is None
            else:
                assert batch_rel is not None
                assert batch_rel["hash"] == ind_rel["hash"]

            # paragraphs 一致
            ind_para_hashes = {p["hash"] for p in ind_paras}
            batch_para_hashes = {p["hash"] for p in batch_paras.get(rh, [])}
            assert ind_para_hashes == batch_para_hashes

    def test_batch_empty_input(self, store_and_seed):
        """空 relation_hashes 返回空 dict。"""
        store, _ = store_and_seed
        assert store.get_relations_by_hashes([], include_inactive=False) == {}
        assert store.get_paragraphs_by_relation_hashes([]) == {}

    def test_batch_nonexistent_hash(self, store_and_seed):
        """不存在的 hash 返回 None/空列表。"""
        store, _ = store_and_seed
        rels = store.get_relations_by_hashes(["nonexistent"], include_inactive=False)
        assert rels.get("nonexistent") is None

        paras = store.get_paragraphs_by_relation_hashes(["nonexistent"])
        assert paras.get("nonexistent", []) == []

    def test_none_filtering_consistent(self, store_and_seed):
        """None 过滤一致：缺失 relation_hash 的候选被跳过。"""
        store, seed = store_and_seed
        valid_rh = seed["relation_hashes"][0]
        mixed_hashes = [valid_rh, "nonexistent_1", "nonexistent_2"]

        batch_rels = store.get_relations_by_hashes(mixed_hashes, include_inactive=False)
        # nonexistent 不在 dict 中（或值为 None）→ 调用方 continue 跳过
        assert batch_rels[valid_rh] is not None
        assert batch_rels.get("nonexistent_1") is None
        assert batch_rels.get("nonexistent_2") is None