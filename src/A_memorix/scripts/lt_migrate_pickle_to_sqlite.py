"""一次性迁移: graph_metadata.pkl → SQLite graph_nodes/graph_edges 表。

用法:
    uv run python -m A_memorix.scripts.lt_migrate_pickle_to_sqlite <data_dir>

    data_dir 应为 A_memorix 插件数据根目录（包含 graph/ 和 metadata/ 子目录）。
"""

import json
import pickle
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path


def migrate(metadata_db: Path, pickle_path: Path) -> None:
    """将 graph_metadata.pkl 中的节点与边元数据迁入 SQLite。"""
    if not pickle_path.exists():
        print(f"pickle 文件不存在，跳过: {pickle_path}")
        return

    backup = pickle_path.with_suffix(".pkl.bak")
    shutil.copy2(pickle_path, backup)
    print(f"备份: {pickle_path} → {backup}")

    with open(pickle_path, "rb") as f:
        data = pickle.load(f)

    conn = sqlite3.connect(str(metadata_db))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    # 确保图存储表存在（兼容已存在或新建的 DB）
    _ensure_graph_tables(conn)

    nodes = data.get("nodes", [])
    node_attrs = data.get("node_attrs", {})

    # 迁移节点
    node_count = 0
    for node_name in nodes:
        # node_name 是原始节点名，node_attrs 的 key 是规范化后的名称
        # 先找原始名，找不到再尝试规范化查找
        attrs = node_attrs.get(node_name)
        if attrs is None and node_name:
            attrs = node_attrs.get(node_name.strip().lower())
        attributes_json = json.dumps(attrs if attrs else {}, ensure_ascii=False)
        conn.execute(
            "INSERT OR REPLACE INTO graph_nodes (node_id, node_type, attributes_json) VALUES (?, ?, ?)",
            (str(node_name), "entity", attributes_json),
        )
        node_count += 1

    # 迁移边（从 edge_hash_map）
    edge_hash_map = data.get("edge_hash_map", {})
    edge_count = 0
    for (src_idx, tgt_idx), hashes in edge_hash_map.items():
        src_idx = int(src_idx)
        tgt_idx = int(tgt_idx)
        if src_idx < 0 or tgt_idx < 0:
            continue
        if src_idx >= len(nodes) or tgt_idx >= len(nodes):
            continue
        src_name = nodes[src_idx]
        tgt_name = nodes[tgt_idx]
        metadata_json = json.dumps(
            {"relation_hashes": sorted(set(str(h) for h in hashes if h))},
            ensure_ascii=False,
        )
        conn.execute(
            "INSERT OR IGNORE INTO graph_edges "
            "(source_node_id, target_node_id, edge_type, weight, metadata_json) "
            "VALUES (?, ?, ?, ?, ?)",
            (str(src_name), str(tgt_name), "related", 1.0, metadata_json),
        )
        edge_count += 1

    # 更新 schema 版本到 2
    conn.execute(
        "INSERT OR REPLACE INTO schema_migrations (version, applied_at) VALUES (?, ?)",
        (2, datetime.now().timestamp()),
    )

    conn.commit()
    conn.close()
    print(f"迁移完成: {node_count} nodes, {edge_count} edges")


def _ensure_graph_tables(conn: sqlite3.Connection) -> None:
    """确保 graph_nodes / graph_edges 表存在。"""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS graph_nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            node_id TEXT NOT NULL UNIQUE,
            node_type TEXT NOT NULL DEFAULT 'entity',
            attributes_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS graph_edges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_node_id TEXT NOT NULL,
            target_node_id TEXT NOT NULL,
            edge_type TEXT NOT NULL DEFAULT 'related',
            weight REAL NOT NULL DEFAULT 1.0,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_graph_nodes_type ON graph_nodes(node_type);
        CREATE INDEX IF NOT EXISTS idx_graph_edges_source ON graph_edges(source_node_id);
        CREATE INDEX IF NOT EXISTS idx_graph_edges_target ON graph_edges(target_node_id);
    """)


def main() -> None:
    if len(sys.argv) < 2:
        print(f"用法: {sys.argv[0]} <data_dir>")
        print("  data_dir: A_memorix 插件数据根目录（包含 graph/ 和 metadata/ 子目录）")
        sys.exit(1)

    data_dir = Path(sys.argv[1])
    if not data_dir.is_dir():
        print(f"错误: 数据目录不存在: {data_dir}")
        sys.exit(1)

    pickle_path = data_dir / "graph" / "graph_metadata.pkl"
    metadata_db = data_dir / "metadata" / "metadata.db"

    if not metadata_db.exists():
        print(f"错误: metadata.db 不存在: {metadata_db}")
        print("请先运行一次应用以创建 metadata.db，或手动创建。")
        sys.exit(1)

    migrate(metadata_db, pickle_path)


if __name__ == "__main__":
    main()
