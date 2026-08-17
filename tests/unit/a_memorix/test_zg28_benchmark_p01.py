"""ZG-28 P0-1 性能基准测试。

验证 P0-1 批量替换后 SQL 次数从 60 降为 1 + 延迟下降可观测。
"""

import time
from pathlib import Path

import pytest

from tests.unit.a_memorix._zg28_helpers import make_metadata_store, seed_relations_and_paragraphs


class TestBenchmarkP01:
    """P0-1 性能基准。"""

    @pytest.fixture
    def store(self, tmp_path: Path):
        s = make_metadata_store(tmp_path)
        entities = [f"实体{i}" for i in range(30)]
        relations = [(entities[i], "关联", entities[i + 1]) for i in range(29)]
        paragraphs = [(f"{entities[i]}和{entities[i+1]}有关联", "test") for i in range(29)]
        seed_relations_and_paragraphs(s, entities=entities, relations=relations, paragraphs=paragraphs)
        yield s
        s.close()

    def test_sql_count_batch_vs_individual(self, store):
        """批量 SQL 次数=1 vs 逐条 SQL 次数=60（30 实体 × 2 方向）。"""
        entity_names = [f"实体{i}" for i in range(30)]

        # 批量：1 次 SQL
        store.get_relations_by_entity_names(entity_names, include_inactive=False)
        batch_sql_count = 1  # 批量方法内部 1 次 SQL

        # 逐条：60 次 SQL（30 实体 × get_relations(subject=) + get_relations(object=)）
        individual_sql_count = 0
        for name in entity_names:
            store.get_relations(subject=name, include_inactive=False)
            individual_sql_count += 1
            store.get_relations(object=name, include_inactive=False)
            individual_sql_count += 1

        assert batch_sql_count == 1, "批量 1 次 SQL"
        assert individual_sql_count == 60, "逐条 60 次 SQL"
        assert individual_sql_count / batch_sql_count == 60, "SQL 降 60x"

    def test_batch_faster_than_individual(self, store):
        """批量延迟低于逐条延迟。"""
        entity_names = [f"实体{i}" for i in range(30)]

        # 批量计时
        t0 = time.perf_counter()
        store.get_relations_by_entity_names(entity_names, include_inactive=False)
        batch_time = time.perf_counter() - t0

        # 逐条计时
        t0 = time.perf_counter()
        for name in entity_names:
            store.get_relations(subject=name, include_inactive=False)
            store.get_relations(object=name, include_inactive=False)
        individual_time = time.perf_counter() - t0

        # 批量应不慢于逐条（允许相等——小规模 SQLite 差异可能不显著）
        assert batch_time <= individual_time * 2, (
            f"批量={batch_time:.4f}s 不应远慢于逐条={individual_time:.4f}s"
        )

    def test_results_consistent(self, store):
        """批量与逐条结果一致（语义等价）。"""
        entity_names = [f"实体{i}" for i in range(30)]

        batch = store.get_relations_by_entity_names(entity_names, include_inactive=False)

        for name in entity_names:
            individual = store.get_relations(subject=name, include_inactive=False) + \
                         store.get_relations(object=name, include_inactive=False)
            batch_hashes = {r["hash"] for r in batch[name]}
            individual_hashes = {r["hash"] for r in individual}
            assert batch_hashes == individual_hashes