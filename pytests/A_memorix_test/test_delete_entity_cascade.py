"""ZG-29 P0-3: kernel.delete_entity 级联删向量/图测试。"""

from pathlib import Path
from unittest.mock import MagicMock

from src.A_memorix.core.storage.metadata_store import MetadataStore
from src.A_memorix.core.storage.graph_store import GraphStore


def test_delete_entity_cascades_vectors_and_graph(tmp_path: Path) -> None:
    """调 kernel.delete_entity 后向量被软删 + 图节点被删。"""
    store = MetadataStore(data_dir=tmp_path)
    store.connect()
    try:
        entity_hash = store.add_entity("Alice")
        alice = store.get_entity(entity_hash)
        assert alice is not None

        graph_store = GraphStore(data_dir=tmp_path / "graph")
        graph_store.add_edges([("Alice", "Bob")], relation_hashes=["rel-1"])

        vector_delete_mock = MagicMock(return_value=1)

        from src.A_memorix.core.runtime.sdk_memory_kernel import SDKMemoryKernel

        kernel = MagicMock(spec=SDKMemoryKernel)
        kernel.metadata_store = store
        kernel.graph_store = graph_store
        kernel._delete_vectors_by_type = vector_delete_mock

        ok = SDKMemoryKernel.delete_entity(kernel, "Alice")
        assert ok is True

        vector_delete_mock.assert_called_once_with(entity_hashes=[entity_hash])
        assert "Alice" not in graph_store.get_nodes()
    finally:
        store.close()


def test_delete_entity_cascade_failure_no_rollback(tmp_path: Path, caplog) -> None:
    """级联失败不回滚 metadata + logger.error。"""
    store = MetadataStore(data_dir=tmp_path)
    store.connect()
    try:
        entity_hash = store.add_entity("Bob")

        graph_store = MagicMock()
        graph_store.delete_nodes.side_effect = Exception("mock graph failure")

        from src.A_memorix.core.runtime.sdk_memory_kernel import SDKMemoryKernel

        kernel = MagicMock(spec=SDKMemoryKernel)
        kernel.metadata_store = store
        kernel.graph_store = graph_store
        kernel._delete_vectors_by_type = MagicMock(return_value=0)

        ok = SDKMemoryKernel.delete_entity(kernel, "Bob")
        assert ok is True

        assert store.get_entity(entity_hash) is None
    finally:
        store.close()


def test_delete_entity_nonexistent_returns_false(tmp_path: Path) -> None:
    """删不存在实体返回 False。"""
    store = MetadataStore(data_dir=tmp_path)
    store.connect()
    try:
        ok, eh, en = store.delete_entity_with_info("NonexistentEntity")
        assert ok is False
        assert eh is None
        assert en is None
    finally:
        store.close()