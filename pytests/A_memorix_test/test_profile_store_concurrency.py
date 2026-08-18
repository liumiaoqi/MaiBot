"""P0-1 profile 版本号竞态可复现测试——显式事务+重试（ZG-30）。"""

import asyncio
from pathlib import Path

from src.A_memorix.core.storage.metadata_store import MetadataStore


def test_version_race(tmp_path: Path) -> None:
    """20 线程并发 upsert_person_profile_snapshot 同一 person_id。

    修复前：裸 SELECT max→INSERT，并发读到相同 max(version)，
            UNIQUE(person_id, profile_version) IntegrityError 未捕获。
    修复后：显式事务 BEGIN IMMEDIATE + IntegrityError 重试，version 单调递增 1~20。
    """
    store = MetadataStore(data_dir=tmp_path)
    store.connect()
    try:
        person_id = "test_person"

        async def run_concurrent_upserts() -> None:
            async def upsert_one(idx: int) -> None:
                def _upsert() -> None:
                    store.profiles.upsert_person_profile_snapshot(
                        person_id=person_id,
                        profile_text=f"profile_text_{idx}",
                    )

                await asyncio.to_thread(_upsert)

            await asyncio.gather(*(upsert_one(i) for i in range(20)))

        asyncio.run(run_concurrent_upserts())

        cursor = store._conn.cursor()
        cursor.execute(
            "SELECT profile_version FROM person_profile_snapshots WHERE person_id=? ORDER BY profile_version",
            (person_id,),
        )
        versions = [row[0] for row in cursor.fetchall()]
    finally:
        store.close()

    assert len(versions) == 20
    assert versions == list(range(1, 21))