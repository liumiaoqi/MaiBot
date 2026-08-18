"""P0-5 并发写可复现测试——threading.Lock 保护写（ZG-30）。"""

import asyncio
import sqlite3
from pathlib import Path

from src.A_memorix.core.storage.metadata_store import MetadataStore


def test_concurrent_write_lock(tmp_path: Path) -> None:
    """50 线程并发写 relation，threading.Lock 互斥写应无 OperationalError。

    修复前：单连接无锁，并发 commit 可能 database is locked。
    修复后：threading.Lock 互斥写，50 条 relation 全部落库。
    """
    store = MetadataStore(data_dir=tmp_path)
    store.connect()
    try:
        async def run_concurrent_writes() -> None:
            async def write_one(idx: int) -> str:
                def _write() -> str:
                    return store.add_relation(
                        f"subject_{idx}", "predicate", f"object_{idx}",
                        source_paragraph=None,
                    )

                return await asyncio.to_thread(_write)

            hashes = await asyncio.gather(*(write_one(i) for i in range(50)))
            return hashes

        hashes = asyncio.run(run_concurrent_writes())

        cursor = store._conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM relations")
        count = cursor.fetchone()[0]
    finally:
        store.close()

    assert len(hashes) == 50
    assert len(set(hashes)) == 50
    assert count >= 50


def test_write_lock_exists(tmp_path: Path) -> None:
    """MetadataStore 初始化后有 _write_lock 属性。"""
    store = MetadataStore(data_dir=tmp_path)
    store.connect()
    try:
        assert hasattr(store, "_write_lock")
        assert store._write_lock is not None
        assert hasattr(store.relations, "_write_lock")
        assert hasattr(store.profiles, "_write_lock")
        assert hasattr(store.paragraphs, "_write_lock")
        assert hasattr(store.entities, "_write_lock")
        assert store.relations._write_lock is store._write_lock
        assert store.profiles._write_lock is store._write_lock
    finally:
        store.close()