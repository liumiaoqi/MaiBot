"""ZG-29 P0-2: graph_store.delete_nodes 级联删 graph_edges 测试。"""

from pathlib import Path

import pytest

from src.A_memorix.core.storage.graph_store import GraphStore


def test_delete_nodes_cascades_graph_edges(tmp_path: Path) -> None:
    """删节点后 graph_edges 表中无涉及该节点的边。"""
    data_dir = tmp_path / "graph"
    store = GraphStore(data_dir=data_dir)
    store.add_edges([("Alice", "Bob")], relation_hashes=["rel-1"])
    store.add_edges([("Bob", "Carol")], relation_hashes=["rel-2"])
    store.add_edges([("Alice", "Carol")], relation_hashes=["rel-3"])

    assert store.num_nodes == 3

    deleted = store.delete_nodes(["Bob"])
    assert deleted == 1

    if store._conn is not None:
        edges = store._conn.execute(
            "SELECT source_node_id, target_node_id FROM graph_edges"
        ).fetchall()
        for src, tgt in edges:
            assert src != "Bob"
            assert tgt != "Bob"

    assert "Bob" not in store.get_nodes()


def test_delete_nodes_preserves_unrelated_edges(tmp_path: Path) -> None:
    """删节点不影响不涉及该节点的边。"""
    data_dir = tmp_path / "graph"
    store = GraphStore(data_dir=data_dir)
    store.add_edges([("Alice", "Bob")], relation_hashes=["rel-1"])
    store.add_edges([("Carol", "Dave")], relation_hashes=["rel-2"])

    store.delete_nodes(["Alice"])

    if store._conn is not None:
        edges = store._conn.execute(
            "SELECT source_node_id, target_node_id FROM graph_edges"
        ).fetchall()
        edge_pairs = {(src, tgt) for src, tgt in edges}
        assert ("Carol", "Dave") in edge_pairs


def test_memory_and_sqlite_consistency_after_delete(tmp_path: Path) -> None:
    """内存邻接矩阵与 SQLite graph_edges 一致。"""
    data_dir = tmp_path / "graph"
    store = GraphStore(data_dir=data_dir)
    store.add_edges([("Alice", "Bob")], relation_hashes=["rel-1"])
    store.add_edges([("Bob", "Carol")], relation_hashes=["rel-2"])

    store.delete_nodes(["Bob"])

    assert "Bob" not in store.get_nodes()
    assert store.num_nodes == 2

    if store._conn is not None:
        sqlite_edges = store._conn.execute(
            "SELECT COUNT(*) FROM graph_edges"
        ).fetchone()[0]
        assert sqlite_edges == 0