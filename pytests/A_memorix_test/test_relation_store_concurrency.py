"""P0-2 relation metadata RMW 竞态可复现测试——显式事务+重试（ZG-30）。"""

import asyncio
from pathlib import Path

from src.A_memorix.core.storage.metadata_store import MetadataStore


def test_metadata_rmw_race(tmp_path: Path) -> None:
    """20 线程并发 patch 同一 relation metadata。

    修复前：裸 SELECT→merge→UPDATE，并发读到相同 metadata，
            last-write-wins 丢失更新（只保留最后一个 patch）。
    修复后：显式事务 BEGIN IMMEDIATE + OperationalError 重试，所有 patch 均合并。
    """
    store = MetadataStore(data_dir=tmp_path)
    store.connect()
    try:
        rel_hash = store.add_relation("Alice", "持有", "地图")

        async def run_concurrent_patches() -> None:
            async def patch_one(idx: int) -> None:
                def _patch() -> None:
                    store.relations.update_relation_metadata(
                        rel_hash, {f"key_{idx}": f"value_{idx}"}
                    )

                await asyncio.to_thread(_patch)

            await asyncio.gather(*(patch_one(i) for i in range(20)))

        asyncio.run(run_concurrent_patches())

        relation = store.get_relation(rel_hash)
    finally:
        store.close()

    assert relation is not None
    metadata = relation["metadata"]
    for i in range(20):
        assert metadata.get(f"key_{i}") == f"value_{i}", f"key_{i} 丢失——RMW 竞态未修复"