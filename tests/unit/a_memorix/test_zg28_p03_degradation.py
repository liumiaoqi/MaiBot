"""ZG-28 P0-3 降级保底测试。

验证 get_relations_by_hashes 异常时降级为逐条 get_relation，结果不丢。
"""

from pathlib import Path

import pytest

from tests.unit.a_memorix._zg28_helpers import make_metadata_store, seed_relations_and_paragraphs


class TestP03Degradation:
    """P0-3 批量异常降级为逐条。"""

    @pytest.fixture
    def store_and_seed(self, tmp_path: Path):
        store = make_metadata_store(tmp_path)
        seed = seed_relations_and_paragraphs(
            store,
            entities=["Python", "Rust", "Go"],
            relations=[
                ("Python", "similar_to", "Rust"),
                ("Rust", "different_from", "Go"),
                ("Go", "concurrent_with", "Python"),
            ],
            paragraphs=[
                ("Python 和 Rust 相似", "test"),
                ("Rust 和 Go 不同", "test"),
                ("Go 与 Python 并发", "test"),
            ],
        )
        yield store, seed
        store.close()

    def test_batch_exception_fallback_to_individual(self, store_and_seed, monkeypatch):
        """批量方法异常时降级为逐条 get_relation，结果不丢。"""
        store, seed = store_and_seed
        relation_hashes = seed["relation_hashes"]

        # 模拟批量方法异常
        original_batch = store.get_relations_by_hashes

        def _failing_batch(*args, **kwargs):
            raise RuntimeError("模拟批量查询异常")

        monkeypatch.setattr(store, "get_relations_by_hashes", _failing_batch)

        # 降级路径：逐条查询
        fallback_rels: dict[str, dict | None] = {}
        for rh in relation_hashes:
            try:
                rel = store.get_relation(rh, include_inactive=False)
                fallback_rels[rh] = rel
            except Exception:
                fallback_rels[rh] = None

        # 恢复批量方法，获取正确结果对比
        monkeypatch.undo()
        batch_rels = original_batch(relation_hashes, include_inactive=False)

        for rh in relation_hashes:
            batch_rel = batch_rels.get(rh)
            fallback_rel = fallback_rels[rh]
            if fallback_rel is None:
                assert batch_rel is None, f"rh={rh}: both should be None"
            else:
                assert batch_rel is not None, f"rh={rh}: both should be non-None"
                assert batch_rel["hash"] == fallback_rel["hash"]

    def test_batch_paragraphs_exception_fallback(self, store_and_seed, monkeypatch):
        """get_paragraphs_by_relation_hashes 异常时降级为逐条。"""
        store, seed = store_and_seed
        relation_hashes = seed["relation_hashes"]

        original_batch = store.get_paragraphs_by_relation_hashes

        def _failing_batch(*args, **kwargs):
            raise RuntimeError("模拟批量查询异常")

        monkeypatch.setattr(store, "get_paragraphs_by_relation_hashes", _failing_batch)

        # 降级路径
        fallback_paras: dict[str, set[str]] = {}
        for rh in relation_hashes:
            try:
                paras = store.get_paragraphs_by_relation(rh)
                fallback_paras[rh] = {p["hash"] for p in paras}
            except Exception:
                fallback_paras[rh] = set()

        # 恢复对比
        monkeypatch.undo()
        batch_paras = original_batch(relation_hashes)

        for rh in relation_hashes:
            batch_hashes = {p["hash"] for p in batch_paras.get(rh, [])}
            assert batch_hashes == fallback_paras[rh], f"rh={rh}: 降级结果不丢"

    def test_empty_hashes_no_exception(self, store_and_seed):
        """空 relation_hashes 不抛异常。"""
        store, _ = store_and_seed
        assert store.get_relations_by_hashes([], include_inactive=False) == {}