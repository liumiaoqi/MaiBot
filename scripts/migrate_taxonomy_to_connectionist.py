"""分类学→连接主义 一次性数据迁移脚本。

用法: python scripts/migrate_taxonomy_to_connectionist.py [--data-dir PATH] [--agent-id AGENT_ID]

从分类学 SQLite 读取 Paragraph/Entity/Relation/Episode 数据，
通过 DataConverter 转换为连接主义 Trace 写入 TraceStore。
支持断点续传（已迁移的 observation_id 不会重复处理）。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.common.logger import get_logger

logger = get_logger("MigrateTaxonomy")


def _find_sqlite_db(data_dir: Path) -> Path | None:
    candidates = [
        data_dir / "a_memorix.db",
        data_dir / "memory.db",
        data_dir / "metadata.db",
    ]
    for p in candidates:
        if p.exists():
            return p
    for p in data_dir.iterdir():
        if p.suffix == ".db" and p.exists():
            return p
    return None


def _load_migrated_ids(progress_file: Path) -> set[str]:
    if not progress_file.exists():
        return set()
    try:
        data = json.loads(progress_file.read_text(encoding="utf-8"))
        return set(data.get("migrated_ids", []))
    except Exception:
        return set()


def _save_migrated_ids(progress_file: Path, ids: set[str]) -> None:
    data = {"migrated_ids": sorted(ids)}
    progress_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


async def run_migration(data_dir: Path, agent_id: str) -> None:
    db_path = _find_sqlite_db(data_dir)
    if db_path is None:
        logger.error(f"未找到分类学 SQLite 数据库: {data_dir}")
        return

    connectionist_dir = data_dir / "connectionist"
    connectionist_dir.mkdir(parents=True, exist_ok=True)

    from src.A_memorix.core.connectionist.concept_index import ConceptIndex
    from src.A_memorix.core.connectionist.trace_store import TraceStore
    from src.A_memorix.core.extraction.llm_concept_extractor import LLMConceptExtractor
    from src.A_memorix.core.migration.data_converter import DataConverter

    trace_store = TraceStore(data_dir)
    concept_index = ConceptIndex(data_dir)
    llm_extractor = LLMConceptExtractor(concept_index=concept_index)
    converter = DataConverter(trace_store, concept_index, llm_extractor)

    progress_file = data_dir / "connectionist" / "migration_progress.json"
    migrated_ids = _load_migrated_ids(progress_file)

    stats = {"total": 0, "success": 0, "failed": 0, "skipped": 0}

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    try:
        cursor = conn.cursor()

        for table_name in ["entities", "paragraphs", "relations", "episodes"]:
            try:
                cursor.execute(f"SELECT * FROM {table_name}")
            except sqlite3.OperationalError:
                logger.warning(f"表 {table_name} 不存在，跳过")
                continue

            rows = cursor.fetchall()
            for row in rows:
                row_dict = dict(row)
                stats["total"] += 1

                if table_name == "entities":
                    try:
                        await converter.convert_entity(row_dict)
                        stats["success"] += 1
                    except Exception as e:
                        logger.error(f"Entity 迁移失败: {e}")
                        stats["failed"] += 1
                    continue

                obs_id_prefix = {
                    "paragraphs": "migrated_p_",
                    "relations": "migrated_r_",
                    "episodes": "migrated_e_",
                }.get(table_name, "migrated_")
                obs_id = f"{obs_id_prefix}{row_dict.get('hash', '')}"

                if obs_id in migrated_ids:
                    stats["skipped"] += 1
                    continue

                try:
                    if table_name == "paragraphs":
                        traces = await converter.convert_paragraph(row_dict, agent_id)
                    elif table_name == "relations":
                        traces = await converter.convert_relation(row_dict, agent_id)
                    elif table_name == "episodes":
                        traces = await converter.convert_episode(row_dict, agent_id)
                    else:
                        traces = []

                    if traces:
                        stats["success"] += 1
                        migrated_ids.add(obs_id)
                    else:
                        stats["skipped"] += 1
                except Exception as e:
                    logger.error(f"{table_name} 迁移失败 (obs_id={obs_id}): {e}")
                    stats["failed"] += 1

        _save_migrated_ids(progress_file, migrated_ids)

    finally:
        conn.close()

    logger.info(
        f"迁移完成: 总计={stats['total']} 成功={stats['success']} "
        f"失败={stats['failed']} 跳过={stats['skipped']}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="分类学→连接主义数据迁移")
    parser.add_argument("--data-dir", type=str, default="data/a_memorix", help="A_memorix 数据目录")
    parser.add_argument("--agent-id", type=str, default="", help="默认智能体 ID")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        logger.error(f"数据目录不存在: {data_dir}")
        sys.exit(1)

    asyncio.run(run_migration(data_dir, args.agent_id))


if __name__ == "__main__":
    main()