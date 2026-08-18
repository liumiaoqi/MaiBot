"""P0-3 跨存储半提交可复现测试——graph_synced 补偿（ZG-30）。"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.A_memorix.core.storage.metadata_store import MetadataStore
from src.A_memorix.core.utils.relation_write_service import RelationWriteService


def test_cross_store_half_commit(tmp_path: Path) -> None:
    """graph 写失败时 metadata 仍可用，graph_synced=false 标记待补偿。

    对标 dsh "Dispose must reach quiescence" + Saga 补偿事务。
    """
    store = MetadataStore(data_dir=tmp_path)
    store.connect()
    try:
        graph_store = MagicMock()
        graph_store.add_edges.side_effect = Exception("mock graph failure")

        vector_store = MagicMock()
        embedding_manager = MagicMock()

        svc = RelationWriteService(
            metadata_store=store,
            graph_store=graph_store,
            vector_store=vector_store,
            embedding_manager=embedding_manager,
        )

        import asyncio

        result = asyncio.run(
            svc.upsert_relation_with_vector(
                "Alice", "持有", "地图",
                confidence=0.8,
                write_vector=False,
            )
        )

        relation = store.get_relation(result.hash_value)
        assert relation is not None
        assert relation["metadata"].get("graph_synced") is False
    finally:
        store.close()


def test_cross_store_compensation_recovery(tmp_path: Path) -> None:
    """graph 写失败后补偿恢复：第二次 add_edges 成功 → graph_synced=true。"""
    store = MetadataStore(data_dir=tmp_path)
    store.connect()
    try:
        call_count = [0]
        graph_store = MagicMock()

        def _add_edges(edges, weights=None, relation_hashes=None):
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("mock first failure")

        graph_store.add_edges.side_effect = _add_edges

        vector_store = MagicMock()
        embedding_manager = MagicMock()

        svc = RelationWriteService(
            metadata_store=store,
            graph_store=graph_store,
            vector_store=vector_store,
            embedding_manager=embedding_manager,
        )

        import asyncio

        result = asyncio.run(
            svc.upsert_relation_with_vector(
                "Bob", "持有", "咖啡",
                confidence=0.9,
                write_vector=False,
            )
        )

        relation = store.get_relation(result.hash_value)
        assert relation["metadata"].get("graph_synced") is False

        call_count[0] = 0
        graph_store.add_edges.side_effect = None

        asyncio.run(svc.compensate_graph_sync())

        relation = store.get_relation(result.hash_value)
        assert relation["metadata"].get("graph_synced") is True
    finally:
        store.close()


def test_cross_store_success_marks_synced(tmp_path: Path) -> None:
    """graph 写成功时 graph_synced=true。"""
    store = MetadataStore(data_dir=tmp_path)
    store.connect()
    try:
        graph_store = MagicMock()
        vector_store = MagicMock()
        embedding_manager = MagicMock()

        svc = RelationWriteService(
            metadata_store=store,
            graph_store=graph_store,
            vector_store=vector_store,
            embedding_manager=embedding_manager,
        )

        import asyncio

        result = asyncio.run(
            svc.upsert_relation_with_vector(
                "Carol", "持有", "茶",
                confidence=1.0,
                write_vector=False,
            )
        )

        relation = store.get_relation(result.hash_value)
        assert relation["metadata"].get("graph_synced") is True

        assert graph_store.add_edges.called
        call_kwargs = graph_store.add_edges.call_args
        assert call_kwargs.kwargs.get("weights") == [1.0]
    finally:
        store.close()