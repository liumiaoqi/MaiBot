from __future__ import annotations

import pickle
from pathlib import Path

import pytest

try:
    from src.A_memorix.core.storage.graph_store import GraphStore
except SystemExit as exc:
    GraphStore = None  # type: ignore[assignment]
    IMPORT_ERROR = f"config initialization exited during import: {exc}"
else:
    IMPORT_ERROR = None


pytestmark = pytest.mark.skipif(IMPORT_ERROR is not None, reason=IMPORT_ERROR or "")


def _build_empty_graph_metadata() -> dict:
    return {
        "nodes": [],
        "node_to_idx": {},
        "node_attrs": {},
        "matrix_format": "csr",
        "total_nodes_added": 0,
        "total_edges_added": 0,
        "total_nodes_deleted": 0,
        "total_edges_deleted": 0,
        "edge_hash_map": {},
    }


def test_graph_store_clear_save_removes_stale_adjacency(tmp_path: Path) -> None:
    data_dir = tmp_path / "graph_data"
    store = GraphStore(data_dir=data_dir)
    store.add_edges([("Alice", "Bob")], relation_hashes=["rel-1"])
    store.save()

    matrix_path = data_dir / "graph_adjacency.npz"
    assert matrix_path.exists()

    store.clear()
    store.save()

    assert not matrix_path.exists()


def test_graph_store_load_resets_stale_adjacency_when_metadata_is_empty(tmp_path: Path) -> None:
    data_dir = tmp_path / "graph_data"
    store = GraphStore(data_dir=data_dir)
    store.add_edges([("Alice", "Bob")], relation_hashes=["rel-1"])
    store.save()

    metadata_path = data_dir / "graph_metadata.pkl"
    with metadata_path.open("wb") as handle:
        pickle.dump(_build_empty_graph_metadata(), handle)

    reloaded = GraphStore(data_dir=data_dir)
    reloaded.load()

    assert reloaded.num_nodes == 0
    assert reloaded.num_edges == 0
    assert reloaded.get_nodes() == []


def test_graph_store_load_clears_stale_edge_hash_map_when_metadata_is_empty(tmp_path: Path) -> None:
    data_dir = tmp_path / "graph_data"
    store = GraphStore(data_dir=data_dir)
    store.add_edges([("Alice", "Bob")], relation_hashes=["rel-1"])
    store.save()

    metadata_path = data_dir / "graph_metadata.pkl"
    empty_metadata = _build_empty_graph_metadata()
    empty_metadata["edge_hash_map"] = {(0, 1): {"rel-1"}}
    with metadata_path.open("wb") as handle:
        pickle.dump(empty_metadata, handle)

    reloaded = GraphStore(data_dir=data_dir)
    reloaded.load()

    assert reloaded.has_edge_hash_map() is False
