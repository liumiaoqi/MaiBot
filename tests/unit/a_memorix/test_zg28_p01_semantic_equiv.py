"""ZG-28 P0-1 语义等价测试：批量 vs 逐条查询结果一致。

验证 get_relations_by_entity_names 批量查询结果与逐条
get_relations(subject=) + get_relations(object=) 合并结果完全一致。
"""

from pathlib import Path

import pytest

from tests.unit.a_memorix._zg28_helpers import make_metadata_store, seed_relations_and_paragraphs


class TestP01SemanticEquiv:
    """P0-1 批量 vs 逐条语义等价。"""

    @pytest.fixture
    def store(self, tmp_path: Path):
        s = make_metadata_store(tmp_path)
        seed_relations_and_paragraphs(
            s,
            entities=["张三", "李四", "王五", "赵六"],
            relations=[
                ("张三", "同事", "李四"),
                ("张三", "朋友", "王五"),
                ("李四", "邻居", "赵六"),
                ("王五", "同学", "张三"),
            ],
            paragraphs=[
                ("张三和李四是同事", "test"),
                ("张三和王五是朋友", "test"),
                ("李四和赵六是邻居", "test"),
                ("王五和张三是同学", "test"),
            ],
        )
        yield s
        s.close()

    def test_batch_equals_individual(self, store):
        """批量 get_relations_by_entity_names 与逐条合并结果一致。"""
        entity_names = ["张三", "李四", "王五"]

        # 批量路径
        batch_result = store.get_relations_by_entity_names(entity_names, include_inactive=False)

        # 逐条路径（模拟降级 fallback）
        individual_result: dict[str, list] = {name: [] for name in entity_names}
        for name in entity_names:
            rels_subj = store.get_relations(subject=name, include_inactive=False)
            rels_obj = store.get_relations(object=name, include_inactive=False)
            seen_hashes: set[str] = set()
            for rel in rels_subj + rels_obj:
                if rel["hash"] not in seen_hashes:
                    seen_hashes.add(rel["hash"])
                    individual_result[name].append(rel)

        # 断言 key 集合一致
        assert set(batch_result.keys()) == set(individual_result.keys())

        # 断言每个 entity 的 relation hash 集合一致
        for name in entity_names:
            batch_hashes = {r["hash"] for r in batch_result[name]}
            individual_hashes = {r["hash"] for r in individual_result[name]}
            assert batch_hashes == individual_hashes, (
                f"entity={name}: batch={batch_hashes} != individual={individual_hashes}"
            )

    def test_batch_covers_all_entities(self, store):
        """批量结果覆盖所有输入 entity_names（无匹配则为空列表）。"""
        result = store.get_relations_by_entity_names(["张三", "不存在"], include_inactive=False)
        assert "张三" in result
        assert "不存在" in result
        assert len(result["张三"]) > 0
        assert result["不存在"] == []

    def test_batch_respects_include_inactive(self, store):
        """include_inactive=False 过滤非活跃关系。"""
        # 标记一个关系为非活跃
        all_rels = store.get_relations(subject="张三", include_inactive=False)
        if all_rels:
            store.mark_relations_inactive([all_rels[0]["hash"]])

        result = store.get_relations_by_entity_names(["张三"], include_inactive=False)
        active_hashes = {r["hash"] for r in result["张三"]}
        assert all_rels[0]["hash"] not in active_hashes, "非活跃关系应被过滤"

    def test_batch_empty_input(self, store):
        """空 entity_names 返回空 dict。"""
        result = store.get_relations_by_entity_names([], include_inactive=False)
        assert result == {}

    def test_batch_single_entity(self, store):
        """单个 entity 批量查询与逐条一致。"""
        batch = store.get_relations_by_entity_names(["赵六"], include_inactive=False)
        individual = store.get_relations(subject="赵六", include_inactive=False) + \
                     store.get_relations(object="赵六", include_inactive=False)
        individual_hashes = {r["hash"] for r in individual}
        batch_hashes = {r["hash"] for r in batch["赵六"]}
        assert batch_hashes == individual_hashes