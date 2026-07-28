"""
Schema 管理器 — 从 MetadataStore 提取的 schema 版本管理与建表逻辑。
"""

import sqlite3
from datetime import datetime

from src.common.logger import get_logger

logger = get_logger("A_Memorix.SchemaManager")

SCHEMA_VERSION = 2


class SchemaManager:
    """
    SQLite schema 生命周期管理。

    职责：
    - 创建所有业务表及索引
    - 校验现有数据库 schema 版本兼容性
    - 不持有连接（由调用方传入）
    """

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def ensure(self, conn: sqlite3.Connection, db_existed: bool) -> None:
        """确保 schema 存在且版本兼容（幂等）。"""
        if not db_existed:
            self.create_tables(conn.cursor())
            conn.commit()
        self.assert_compatible(conn, db_existed=db_existed)

    def create_tables(self, cursor: sqlite3.Cursor) -> None:
        """创建所有业务表、索引，并写入版本信息。"""
        _create_all_tables(cursor)
        _create_performance_indexes(cursor)
        cursor.execute(
            "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
            (SCHEMA_VERSION, datetime.now().timestamp()),
        )

    def assert_compatible(
        self,
        conn: sqlite3.Connection,
        db_existed: bool = True,
    ) -> None:
        """检查 schema 版本是否匹配。"""
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
        )
        has_version_table = cursor.fetchone() is not None
        if not has_version_table:
            if db_existed:
                raise RuntimeError(
                    "检测到旧版 metadata schema（缺少 schema_migrations）。"
                    " 请先执行 scripts/lt_migrate_v15_to_v1.py。"
                )
            return

        cursor.execute("SELECT MAX(version) FROM schema_migrations")
        row = cursor.fetchone()
        version = int(row[0]) if row and row[0] is not None else 0
        if version != SCHEMA_VERSION:
            raise RuntimeError(
                f"metadata schema 版本不匹配: current={version}, expected={SCHEMA_VERSION}。"
                " 请执行 scripts/lt_migrate_pickle_to_sqlite.py 或 scripts/lt_migrate_v15_to_v1.py。"
            )

    def get_schema_version(self, conn: sqlite3.Connection) -> int:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
        )
        if cursor.fetchone() is None:
            return 0
        cursor.execute("SELECT MAX(version) FROM schema_migrations")
        row = cursor.fetchone()
        return int(row[0]) if row and row[0] is not None else 0

    def set_schema_version(
        self,
        conn: sqlite3.Connection,
        version: int = SCHEMA_VERSION,
    ) -> None:
        cursor = conn.cursor()
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version INTEGER PRIMARY KEY, applied_at REAL NOT NULL)"
        )
        cursor.execute(
            "INSERT OR REPLACE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
            (int(version), datetime.now().timestamp()),
        )
        conn.commit()


# =========================================================================
# SQL 常量 — 建表语句
# =========================================================================

def _create_all_tables(cursor: sqlite3.Cursor) -> None:
    """创建所有核心业务表及索引。"""

    # --- 段落表 ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS paragraphs (
            hash TEXT PRIMARY KEY,
            content TEXT NOT NULL,
            vector_index INTEGER,
            created_at REAL,
            updated_at REAL,
            metadata TEXT,
            source TEXT,
            word_count INTEGER,
            event_time REAL,
            event_time_start REAL,
            event_time_end REAL,
            time_granularity TEXT,
            time_confidence REAL DEFAULT 1.0,
            is_permanent BOOLEAN DEFAULT 0,
            last_accessed REAL,
            access_count INTEGER DEFAULT 0,
            is_deleted INTEGER DEFAULT 0,
            deleted_at REAL
        )
    """)

    # --- 实体表 ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS entities (
            hash TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            vector_index INTEGER,
            appearance_count INTEGER DEFAULT 1,
            created_at REAL,
            metadata TEXT,
            is_deleted INTEGER DEFAULT 0,
            deleted_at REAL
        )
    """)

    # --- 关系表 ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS relations (
            hash TEXT PRIMARY KEY,
            subject TEXT NOT NULL,
            predicate TEXT NOT NULL,
            object TEXT NOT NULL,
            vector_index INTEGER,
            confidence REAL DEFAULT 1.0,
            vector_state TEXT DEFAULT 'none',
            vector_updated_at REAL,
            vector_error TEXT,
            vector_retry_count INTEGER DEFAULT 0,
            created_at REAL,
            source_paragraph TEXT,
            metadata TEXT,
            is_permanent BOOLEAN DEFAULT 0,
            last_accessed REAL,
            access_count INTEGER DEFAULT 0,
            is_inactive BOOLEAN DEFAULT 0,
            inactive_since REAL,
            is_pinned BOOLEAN DEFAULT 0,
            protected_until REAL,
            last_reinforced REAL,
            UNIQUE(subject, predicate, object)
        )
    """)

    # --- 回收站关系表 ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS deleted_relations (
            hash TEXT PRIMARY KEY,
            subject TEXT NOT NULL,
            predicate TEXT NOT NULL,
            object TEXT NOT NULL,
            vector_index INTEGER,
            confidence REAL DEFAULT 1.0,
            vector_state TEXT DEFAULT 'none',
            vector_updated_at REAL,
            vector_error TEXT,
            vector_retry_count INTEGER DEFAULT 0,
            created_at REAL,
            source_paragraph TEXT,
            metadata TEXT,
            is_permanent BOOLEAN DEFAULT 0,
            last_accessed REAL,
            access_count INTEGER DEFAULT 0,
            is_inactive BOOLEAN DEFAULT 0,
            inactive_since REAL,
            is_pinned BOOLEAN DEFAULT 0,
            protected_until REAL,
            last_reinforced REAL,
            deleted_at REAL
        )
    """)

    # --- 32位哈希别名映射 ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS relation_hash_aliases (
            alias32 TEXT PRIMARY KEY,
            hash TEXT NOT NULL
        )
    """)

    # --- Schema 版本 ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at REAL NOT NULL
        )
    """)

    # --- 三元组与段落的关联表 ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS paragraph_relations (
            paragraph_hash TEXT NOT NULL,
            relation_hash TEXT NOT NULL,
            PRIMARY KEY (paragraph_hash, relation_hash),
            FOREIGN KEY (paragraph_hash) REFERENCES paragraphs(hash) ON DELETE CASCADE,
            FOREIGN KEY (relation_hash) REFERENCES relations(hash) ON DELETE CASCADE
        )
    """)

    # --- 实体与段落的关联表 ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS paragraph_entities (
            paragraph_hash TEXT NOT NULL,
            entity_hash TEXT NOT NULL,
            mention_count INTEGER DEFAULT 1,
            PRIMARY KEY (paragraph_hash, entity_hash),
            FOREIGN KEY (paragraph_hash) REFERENCES paragraphs(hash) ON DELETE CASCADE,
            FOREIGN KEY (entity_hash) REFERENCES entities(hash) ON DELETE CASCADE
        )
    """)

    # --- 基础索引 ---
    _create_base_indexes(cursor)

    # --- 人物画像相关表 ---
    _create_profile_tables(cursor)

    # --- Episode 情景记忆表 ---
    _create_episode_tables(cursor)

    # --- 图存储节点表 ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS graph_nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            node_id TEXT NOT NULL UNIQUE,
            node_type TEXT NOT NULL DEFAULT 'entity',
            attributes_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    # --- 图存储边表 ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS graph_edges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_node_id TEXT NOT NULL,
            target_node_id TEXT NOT NULL,
            edge_type TEXT NOT NULL DEFAULT 'related',
            weight REAL NOT NULL DEFAULT 1.0,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    # --- 图存储索引 ---
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_graph_nodes_type ON graph_nodes(node_type)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_graph_edges_source ON graph_edges(source_node_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_graph_edges_target ON graph_edges(target_node_id)"
    )

    # --- 队列 / 操作记录表 ---
    _create_queue_tables(cursor)


def _create_base_indexes(cursor: sqlite3.Cursor) -> None:
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_paragraphs_vector ON paragraphs(vector_index)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_entities_vector ON entities(vector_index)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_relations_vector ON relations(vector_index)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_relations_subject ON relations(subject)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_relations_object ON relations(object)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_paragraphs_source ON paragraphs(source)")
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_paragraphs_deleted ON paragraphs(is_deleted, deleted_at)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_entities_deleted ON entities(is_deleted, deleted_at)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_relations_inactive ON relations(is_inactive, inactive_since)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_relations_protected ON relations(is_pinned, protected_until)"
    )


def _create_profile_tables(cursor: sqlite3.Cursor) -> None:
    # 人物画像开关表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS person_profile_switches (
            stream_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 0,
            updated_at REAL NOT NULL,
            PRIMARY KEY (stream_id, user_id)
        )
    """)
    # 人物画像快照表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS person_profile_snapshots (
            snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
            person_id TEXT NOT NULL,
            profile_version INTEGER NOT NULL,
            profile_text TEXT NOT NULL,
            aliases_json TEXT,
            relation_edges_json TEXT,
            vector_evidence_json TEXT,
            evidence_ids_json TEXT,
            updated_at REAL NOT NULL,
            expires_at REAL,
            source_note TEXT,
            UNIQUE(person_id, profile_version)
        )
    """)
    # 活跃人物集合
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS person_profile_active_persons (
            stream_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            person_id TEXT NOT NULL,
            last_seen_at REAL NOT NULL,
            PRIMARY KEY (stream_id, user_id, person_id)
        )
    """)
    # 人物画像覆盖
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS person_profile_overrides (
            person_id TEXT PRIMARY KEY,
            override_text TEXT NOT NULL,
            updated_at REAL NOT NULL,
            updated_by TEXT,
            source TEXT
        )
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_person_profile_switches_enabled "
        "ON person_profile_switches(enabled)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_person_profile_snapshots_person "
        "ON person_profile_snapshots(person_id, updated_at DESC)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_person_profile_active_seen "
        "ON person_profile_active_persons(last_seen_at DESC)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_person_profile_overrides_updated "
        "ON person_profile_overrides(updated_at DESC)"
    )


def _create_episode_tables(cursor: sqlite3.Cursor) -> None:
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS episodes (
            episode_id TEXT PRIMARY KEY,
            source TEXT,
            title TEXT NOT NULL,
            summary TEXT NOT NULL,
            event_time_start REAL,
            event_time_end REAL,
            time_granularity TEXT,
            time_confidence REAL DEFAULT 1.0,
            participants_json TEXT,
            keywords_json TEXT,
            evidence_ids_json TEXT,
            paragraph_count INTEGER DEFAULT 0,
            llm_confidence REAL DEFAULT 0.0,
            segmentation_model TEXT,
            segmentation_version TEXT,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS episode_paragraphs (
            episode_id TEXT NOT NULL,
            paragraph_hash TEXT NOT NULL,
            position INTEGER DEFAULT 0,
            PRIMARY KEY (episode_id, paragraph_hash),
            FOREIGN KEY (episode_id) REFERENCES episodes(episode_id) ON DELETE CASCADE,
            FOREIGN KEY (paragraph_hash) REFERENCES paragraphs(hash) ON DELETE CASCADE
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_episodes_source_time_end
        ON episodes(source, event_time_end DESC)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_episodes_updated_at
        ON episodes(updated_at DESC)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_episode_paragraphs_paragraph
        ON episode_paragraphs(paragraph_hash)
    """)


def _create_queue_tables(cursor: sqlite3.Cursor) -> None:
    # Episode 生成队列
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS episode_pending_paragraphs (
            paragraph_hash TEXT PRIMARY KEY,
            source TEXT,
            created_at REAL,
            status TEXT DEFAULT 'pending',
            retry_count INTEGER DEFAULT 0,
            last_error TEXT,
            updated_at REAL NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS episode_rebuild_sources (
            source TEXT PRIMARY KEY,
            status TEXT DEFAULT 'pending',
            retry_count INTEGER DEFAULT 0,
            last_error TEXT,
            reason TEXT,
            requested_at REAL NOT NULL,
            updated_at REAL NOT NULL
        )
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_episode_pending_status_updated "
        "ON episode_pending_paragraphs(status, updated_at)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_episode_pending_source_created "
        "ON episode_pending_paragraphs(source, created_at)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_episode_rebuild_status_updated "
        "ON episode_rebuild_sources(status, updated_at)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_episode_rebuild_updated_at "
        "ON episode_rebuild_sources(updated_at DESC)"
    )

    # 段落向量回填
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS paragraph_vector_backfill (
            paragraph_hash TEXT PRIMARY KEY,
            status TEXT DEFAULT 'pending',
            retry_count INTEGER DEFAULT 0,
            last_error TEXT,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        )
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_paragraph_vector_backfill_status_updated "
        "ON paragraph_vector_backfill(status, updated_at)"
    )

    # 人物画像刷新队列
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS person_profile_refresh_queue (
            person_id TEXT PRIMARY KEY,
            status TEXT DEFAULT 'pending',
            reason TEXT,
            source_query_tool_id TEXT,
            retry_count INTEGER DEFAULT 0,
            last_error TEXT,
            requested_at REAL NOT NULL,
            updated_at REAL NOT NULL
        )
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_person_profile_refresh_queue_status_updated "
        "ON person_profile_refresh_queue(status, updated_at)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_person_profile_refresh_queue_requested "
        "ON person_profile_refresh_queue(requested_at DESC)"
    )

    # 外部记忆引用
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS external_memory_refs (
            external_id TEXT PRIMARY KEY,
            paragraph_hash TEXT NOT NULL,
            source_type TEXT,
            created_at REAL NOT NULL,
            metadata_json TEXT
        )
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_external_memory_refs_paragraph "
        "ON external_memory_refs(paragraph_hash)"
    )

    # V5 操作日志
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS memory_v5_operations (
            operation_id TEXT PRIMARY KEY,
            action TEXT NOT NULL,
            target TEXT,
            reason TEXT,
            updated_by TEXT,
            created_at REAL NOT NULL,
            resolved_hashes_json TEXT,
            result_json TEXT
        )
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_memory_v5_operations_created "
        "ON memory_v5_operations(created_at DESC)"
    )

    # 删除操作
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS delete_operations (
            operation_id TEXT PRIMARY KEY,
            mode TEXT NOT NULL,
            selector TEXT,
            reason TEXT,
            requested_by TEXT,
            status TEXT NOT NULL,
            created_at REAL NOT NULL,
            restored_at REAL,
            summary_json TEXT
        )
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_delete_operations_created "
        "ON delete_operations(created_at DESC)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_delete_operations_mode "
        "ON delete_operations(mode, created_at DESC)"
    )
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS delete_operation_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            operation_id TEXT NOT NULL,
            item_type TEXT NOT NULL,
            item_hash TEXT,
            item_key TEXT,
            payload_json TEXT,
            created_at REAL NOT NULL,
            FOREIGN KEY (operation_id) REFERENCES delete_operations(operation_id) ON DELETE CASCADE
        )
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_delete_operation_items_operation "
        "ON delete_operation_items(operation_id, id ASC)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_delete_operation_items_hash "
        "ON delete_operation_items(item_hash)"
    )


def _create_performance_indexes(cursor: sqlite3.Cursor) -> None:
    """创建热点查询使用的补充索引。"""
    cursor.execute("PRAGMA table_info(paragraphs)")
    paragraph_columns = {row[1] for row in cursor.fetchall()}
    cursor.execute("PRAGMA table_info(relations)")
    relation_columns = {row[1] for row in cursor.fetchall()}

    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_paragraph_relations_relation "
        "ON paragraph_relations(relation_hash, paragraph_hash)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_paragraph_entities_entity "
        "ON paragraph_entities(entity_hash, paragraph_hash)"
    )
    if {"source", "is_deleted", "created_at", "hash"}.issubset(paragraph_columns):
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_paragraphs_source_live_created "
            "ON paragraphs(source, is_deleted, created_at, hash)"
        )
    if {"subject", "object", "is_inactive"}.issubset(relation_columns):
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_relations_subject_object_active "
            "ON relations(LOWER(TRIM(subject)), LOWER(TRIM(object)), is_inactive)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_relations_object_active "
            "ON relations(LOWER(TRIM(object)), is_inactive)"
        )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_episode_pending_status_retry_updated "
        "ON episode_pending_paragraphs(status, retry_count, updated_at)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_paragraph_vector_backfill_status_retry_updated "
        "ON paragraph_vector_backfill(status, retry_count, updated_at)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_episode_rebuild_status_retry_updated "
        "ON episode_rebuild_sources(status, retry_count, requested_at, updated_at)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_person_profile_refresh_status_retry_updated "
        "ON person_profile_refresh_queue(status, retry_count, requested_at, updated_at)"
    )
