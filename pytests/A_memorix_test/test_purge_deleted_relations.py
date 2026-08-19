"""ZG-29 P0-1: deleted_relations 自动清理测试。"""

import asyncio
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.A_memorix.core.storage.metadata_store import MetadataStore
from src.A_memorix.core.runtime.services.maintenance import MaintenanceService


def _make_maintenance(metadata_store: MetadataStore, cfg_overrides: dict | None = None) -> MaintenanceService:
    cfg_data = {
        "memory.enabled": True,
        "memory.deleted_relations_retention_days": 30,
        "memory.purge_batch_size": 500,
    }
    if cfg_overrides:
        cfg_data.update(cfg_overrides)

    def cfg(key: str, default=None):
        return cfg_data.get(key, default)

    return MaintenanceService(
        get_metadata_store=lambda: metadata_store,
        get_graph_store=lambda: MagicMock(),
        cfg=cfg,
        persist=lambda: None,
        rebuild_graph_from_metadata=lambda: None,
        resolve_relation_hashes=lambda x: [],
        resolve_deleted_relation_hashes=lambda x: [],
        delete_vectors_by_type=lambda **kw: None,
        background_scheduler=MagicMock(),
    )


def test_purge_expired_deleted_relations(tmp_path: Path) -> None:
    """过期记录被物理删除，未过期保留。"""
    store = MetadataStore(data_dir=tmp_path)
    store.connect()
    try:
        now = time.time()
        old_cutoff = now - 40 * 86400
        store.relations._conn.execute(
            "INSERT INTO deleted_relations (hash, subject, predicate, object, confidence, deleted_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("hash_old", "Alice", "knows", "Bob", 0.8, old_cutoff),
        )
        recent_cutoff = now - 1 * 86400
        store.relations._conn.execute(
            "INSERT INTO deleted_relations (hash, subject, predicate, object, confidence, deleted_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("hash_recent", "Carol", "knows", "Dave", 0.9, recent_cutoff),
        )
        store.relations._conn.commit()

        svc = _make_maintenance(store)
        asyncio.run(svc._purge_deleted_relations_phase())

        remaining = store.relations._conn.execute(
            "SELECT hash FROM deleted_relations"
        ).fetchall()
        remaining_hashes = {row[0] for row in remaining}
        assert "hash_old" not in remaining_hashes
        assert "hash_recent" in remaining_hashes
    finally:
        store.close()


def test_purge_batch_size_limit(tmp_path: Path) -> None:
    """分批 ≤500 条。"""
    store = MetadataStore(data_dir=tmp_path)
    store.connect()
    try:
        now = time.time()
        old_cutoff = now - 40 * 86400
        for i in range(600):
            store.relations._conn.execute(
                "INSERT INTO deleted_relations (hash, subject, predicate, object, confidence, deleted_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (f"hash_{i}", f"entity_{i}", "rel", "target", 0.5, old_cutoff),
            )
        store.relations._conn.commit()

        svc = _make_maintenance(store, {"memory.purge_batch_size": 500})
        asyncio.run(svc._purge_deleted_relations_phase())

        remaining_count = store.relations._conn.execute(
            "SELECT COUNT(*) FROM deleted_relations"
        ).fetchone()[0]
        assert remaining_count == 100
    finally:
        store.close()


def test_purge_exception_does_not_crash(tmp_path: Path) -> None:
    """异常不崩溃（出声日志）。"""
    store = MetadataStore(data_dir=tmp_path)
    store.connect()
    try:
        broken_store = MagicMock()
        broken_store.purge_deleted_relations.side_effect = Exception("mock failure")

        svc = MaintenanceService(
            get_metadata_store=lambda: broken_store,
            get_graph_store=lambda: MagicMock(),
            cfg=lambda k, d=None: 30 if "retention" in k else (500 if "batch" in k else d),
            persist=lambda: None,
            rebuild_graph_from_metadata=lambda: None,
            resolve_relation_hashes=lambda x: [],
            resolve_deleted_relation_hashes=lambda x: [],
            delete_vectors_by_type=lambda **kw: None,
            background_scheduler=MagicMock(),
        )

        asyncio.run(svc._purge_deleted_relations_phase())
    finally:
        store.close()