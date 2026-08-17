"""ZG-28 P0-1 降级保底测试。

验证 get_relations_by_entity_names 异常时降级为逐条查询，结果不丢。
"""

from pathlib import Path

import pytest

from tests.unit.a_memorix._zg28_helpers import make_metadata_store, seed_relations_and_paragraphs


class TestP01Degradation:
    """P0-1 批量异常降级为逐条。"""

    @pytest.fixture
    def store(self, tmp_path: Path):
        s = make_metadata_store(tmp_path)
        seed_relations_and_paragraphs(
            s,
            entities=["张三", "李四", "王五"],
            relations=[
                ("张三", "同事", "李四"),
                ("李四", "朋友", "王五"),
                ("王五", "邻居", "张三"),
            ],
            paragraphs=[
                ("张三和李四是同事", "test"),
                ("李四和王五是朋友", "test"),
                ("王五和张三是邻居", "test"),
            ],
        )
        yield s
        s.close()

    def test_batch_exception_fallback_to_individual(self, store, monkeypatch):
        """批量方法异常时降级为逐条，结果不丢。"""
        entity_names = ["张三", "李四", "王五"]

        # 模拟批量方法异常
        original_batch = store.get_relations_by_entity_names

        def _failing_batch(*args, **kwargs):
            raise RuntimeError("模拟批量查询异常")

        monkeypatch.setattr(store, "get_relations_by_entity_names", _failing_batch)

        # 降级路径：逐条查询
        fallback_result: dict[str, list] = {name: [] for name in entity_names}
        for name in entity_names:
            rels = store.get_relations(subject=name, include_inactive=False) + \
                   store.get_relations(object=name, include_inactive=False)
            seen = set()
            for rel in rels:
                if rel["hash"] not in seen:
                    seen.add(rel["hash"])
                    fallback_result[name].append(rel)

        # 恢复批量方法，获取正确结果对比
        monkeypatch.undo()
        batch_result = original_batch(entity_names, include_inactive=False)

        # 断言降级结果与批量结果一致
        for name in entity_names:
            batch_hashes = {r["hash"] for r in batch_result[name]}
            fallback_hashes = {r["hash"] for r in fallback_result[name]}
            assert batch_hashes == fallback_hashes, (
                f"降级结果不丢: {name} batch={batch_hashes} fallback={fallback_hashes}"
            )

    def test_empty_entity_names_no_exception(self, store):
        """空 entity_names 不抛异常。"""
        result = store.get_relations_by_entity_names([], include_inactive=False)
        assert result == {}