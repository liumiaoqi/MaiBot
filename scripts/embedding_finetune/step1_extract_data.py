"""Step 1: 从 A_memorix SQLite 提取全量数据，供人工审核后用于 embedding 微调。

输出（全字段，不过滤）：
  - paragraphs.csv          段落文本（含 source/word_count/knowledge_type 等）
  - episodes.csv            情景记忆（含 title/summary/participants/keywords）
  - relations.csv           关系三元组（含 confidence/is_inactive/is_pinned）
  - entities.csv            实体名（含 appearance_count）
  - person_profiles.csv     人物画像快照（含 profile_text/aliases/relation_edges）
  - paragraph_entities.csv  段落-实体关联（含 mention_count）

用法：
  python step1_extract_data.py [--db PATH] [--out DIR]
"""

import argparse
import csv
import sqlite3
from pathlib import Path

DEFAULT_DB = Path("data/MaiMBot/a-memorix/metadata/metadata.db")
DEFAULT_OUT = Path("scripts/embedding_finetune/data")


def dump_table(conn: sqlite3.Connection, table: str, out_path: Path, where: str = "") -> int:
    rows = conn.execute(f"SELECT * FROM {table} {where}").fetchall()
    cols = [desc[0] for desc in conn.execute(f"SELECT * FROM {table} LIMIT 0").description]
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            w.writerow([r[c] for c in cols])
    return len(rows)


def extract(db_path: Path, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    n = dump_table(conn, "paragraphs", out_dir / "paragraphs.csv", "WHERE is_deleted = 0")
    print(f"paragraphs: {n}")

    n = dump_table(conn, "episodes", out_dir / "episodes.csv")
    print(f"episodes: {n}")

    n = dump_table(conn, "relations", out_dir / "relations.csv")
    print(f"relations: {n}")

    n = dump_table(conn, "entities", out_dir / "entities.csv", "WHERE is_deleted = 0")
    print(f"entities: {n}")

    n = dump_table(conn, "person_profile_snapshots", out_dir / "person_profiles.csv")
    print(f"person_profiles: {n}")

    n = dump_table(conn, "paragraph_entities", out_dir / "paragraph_entities.csv")
    print(f"paragraph_entities: {n}")

    n = dump_table(conn, "paragraph_relations", out_dir / "paragraph_relations.csv")
    print(f"paragraph_relations: {n}")

    n = dump_table(conn, "episode_paragraphs", out_dir / "episode_paragraphs.csv")
    print(f"episode_paragraphs: {n}")

    conn.close()
    print(f"全量数据已写入 {out_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, dest="db_path")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, dest="out_dir")
    args = parser.parse_args()
    extract(args.db_path, args.out_dir)
