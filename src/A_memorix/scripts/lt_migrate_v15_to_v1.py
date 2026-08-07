"""lt3 存储改造 — 将 v15 schema 数据库迁移到 v1 干净 schema。

重置 SCHEMA_VERSION=1，删除旧表，只迁移核心数据。
"""

import sqlite3
import shutil
import sys
from pathlib import Path

def migrate(source_db: Path) -> Path:
    """迁移 v15 database → v1 database，返回新 db 路径。"""
    backup = source_db.with_suffix(".db.v15.bak")
    shutil.copy2(source_db, backup)
    print(f"备份: {source_db} → {backup}")

    dest = source_db.with_suffix(".db.v1")
    if dest.exists():
        dest.unlink()

    src = sqlite3.connect(str(source_db))
    dst = sqlite3.connect(str(dest))

    # 创建 v1 schema（精简版，只包含核心表）
    dst.executescript("""
        PRAGMA journal_mode=WAL;
        PRAGMA foreign_keys=ON;

        CREATE TABLE schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        INSERT INTO schema_version (version) VALUES (1);

        CREATE TABLE paragraphs (
            hash TEXT PRIMARY KEY,
            content TEXT NOT NULL,
            word_count INTEGER DEFAULT 0,
            knowledge_type TEXT DEFAULT 'mixed',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE entities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            type TEXT DEFAULT 'unknown',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE relations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_hash TEXT NOT NULL,
            target_hash TEXT NOT NULL,
            relation_type TEXT NOT NULL,
            confidence REAL DEFAULT 1.0,
            metadata_json TEXT DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE paragraph_entities (
            paragraph_hash TEXT NOT NULL,
            entity_id INTEGER NOT NULL,
            PRIMARY KEY (paragraph_hash, entity_id)
        );

        CREATE TABLE person_profiles (
            person_id TEXT PRIMARY KEY,
            profile_json TEXT NOT NULL DEFAULT '{}',
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE profile_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            person_id TEXT NOT NULL,
            snapshot_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE VIRTUAL TABLE paragraphs_fts USING fts5(
            content,
            content_rowid='rowid'
        );
    """)

    # 迁移核心数据
    tables = src.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    existing = {row[0] for row in tables}

    for table in ["paragraphs", "entities", "relations", "paragraph_entities",
                   "person_profiles", "profile_snapshots"]:
        if table in existing:
            try:
                rows = src.execute(f"SELECT * FROM {table}").fetchall()
                if rows:
                    cols = [d[0] for d in src.execute(f"PRAGMA table_info({table})").fetchall()]
                    placeholders = ", ".join(["?" for _ in cols])
                    dst.executemany(
                        f"INSERT OR IGNORE INTO {table} ({', '.join(cols)}) VALUES ({placeholders})",
                        rows,
                    )
                    print(f"  {table}: {len(rows)} rows migrated")
            except Exception as e:
                from src.core.error_escalation.types import ErrorLevel
                from src.core.error_escalation_port_registry import get_error_escalation_port
                port = get_error_escalation_port()
                if port is not None:
                    port.report(ErrorLevel.WARNING, "迁移表处理失败，已跳过", exception=e)
                print(f"  {table}: SKIPPED ({e})")

    # 迁移 FTS5 数据
    if "paragraphs" in existing:
        try:
            rows = src.execute("SELECT rowid, content FROM paragraphs").fetchall()
            if rows:
                dst.executemany(
                    "INSERT INTO paragraphs_fts(rowid, content) VALUES (?, ?)",
                    [(r[0], r[1]) for r in rows],
                )
                print(f"  paragraphs_fts: {len(rows)} rows indexed")
        except Exception as e:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, "迁移 paragraphs_fts 失败，已跳过", exception=e)
            print(f"  paragraphs_fts: SKIPPED ({e})")

    src.close()
    dst.commit()
    dst.close()

    # 原子替换
    final = source_db.with_suffix(".db")
    shutil.copy2(dest, final)
    print(f"迁移完成: {final}")
    return final


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: python {sys.argv[0]} <metadata.db>")
        sys.exit(1)
    migrate(Path(sys.argv[1]))
