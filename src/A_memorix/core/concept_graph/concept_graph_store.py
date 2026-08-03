"""ConceptGraphStore — 概念图 SQLite 持久化（MF-P1-003）。

单一 DB（concept_graph.db，WAL 模式）承载三张表：
- concept_nodes：节点（概念/实体/同源，统一 id）
- relation_edges：事实投影关系边
- trace_edges：联想投影 Trace 边

R07 修正：内存邻接索引——init_schema() 后从 SQLite 全量加载 trace_edges
到 dict；upsert_trace_edge 写库后同步内存；get_adjacent_traces 优先读内存。
"""

import sqlite3
import threading
import time as _time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from src.common.logger import get_logger

from .models import ConceptNode, DecayResult, EdgeSource, NodeCategory, RelationEdge, TraceEdge

logger = get_logger("A_Memorix.ConceptGraphStore")

_DB_FILE = "concept_graph.db"


class ConceptGraphStore:
    """概念图 SQLite 持久化。"""

    def __init__(self, data_dir: str | Path) -> None:
        self._data_dir = Path(data_dir)
        self._conn = sqlite3.connect(self._data_dir / _DB_FILE, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        # RLock：transaction() 持有写锁期间，内部 upsert_* 再次获取不互锁
        self._write_lock = threading.RLock()
        # R07：内存邻接索引 {concept_id: [TraceEdge, ...]}
        self._adjacency_index: dict[str, list[TraceEdge]] = {}
        # 显式外层事务标志（Python 3.14 sqlite3 隐式事务下 in_transaction 不可靠）
        self._in_outer_transaction = False

    def init_schema(self) -> None:
        """创建三表 + 索引 + 幂等表（幂等）。"""
        with self._write_lock:
            self._conn.executescript(_SCHEMA_SQL)
            self._conn.commit()
            self._rebuild_adjacency_index()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """同一 SQLite 事务（R05：双投影串行写入同一 BEGIN/COMMIT）。

        显式 BEGIN + 标志位：外部事务开启时 upsert_* 不自行 commit。
        """
        with self._write_lock:
            self._conn.execute("BEGIN")
            self._in_outer_transaction = True
            try:
                yield self._conn
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise
            finally:
                self._in_outer_transaction = False

    # ── 写入幂等（event_id 去重） ─────────────────────────

    def has_event_written(self, event_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM event_writes WHERE event_id = ?", (event_id,)
        ).fetchone()
        return row is not None

    def mark_event_written(self, event_id: str) -> None:
        with self._write_lock:
            self._conn.execute(
                "INSERT OR IGNORE INTO event_writes (event_id, written_at) VALUES (?, ?)",
                (event_id, _time.time()),
            )
            if not self._in_outer_transaction:
                self._conn.commit()

    def _rebuild_adjacency_index(self) -> None:
        """从 SQLite 全量加载 trace_edges 到内存邻接索引（R07，双向）。"""
        self._adjacency_index.clear()
        rows = self._conn.execute(
            "SELECT * FROM trace_edges ORDER BY created_at"
        ).fetchall()
        for row in rows:
            edge = self._row_to_trace_edge(row)
            self._adjacency_index.setdefault(edge.source_concept_id, []).append(edge)
            self._adjacency_index.setdefault(edge.target_concept_id, []).append(edge)

    # ── 节点 ──────────────────────────────────────────────

    def upsert_node(self, node: ConceptNode) -> None:
        with self._write_lock:
            self._conn.execute(
                """
                INSERT INTO concept_nodes (id, name, type, embedding, embedding_pending, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    type=excluded.type,
                    embedding=COALESCE(excluded.embedding, concept_nodes.embedding),
                    embedding_pending=excluded.embedding_pending,
                    updated_at=excluded.updated_at
                """,
                (
                    node.id,
                    node.name,
                    node.type.value,
                    node.embedding,
                    int(node.embedding_pending),
                    node.created_at,
                    node.updated_at,
                ),
            )
            if not self._in_outer_transaction:
                self._conn.commit()

    def get_node_by_id(self, node_id: str) -> Optional[ConceptNode]:
        row = self._conn.execute(
            "SELECT * FROM concept_nodes WHERE id = ?", (node_id,)
        ).fetchone()
        return self._row_to_node(row) if row else None

    def get_node_by_name(self, name: str) -> Optional[ConceptNode]:
        row = self._conn.execute(
            "SELECT * FROM concept_nodes WHERE name = ?", (name,)
        ).fetchone()
        return self._row_to_node(row) if row else None

    # ── 关系边（事实投影） ─────────────────────────────────

    def upsert_relation_edge(self, edge: RelationEdge) -> None:
        with self._write_lock:
            self._conn.execute(
                """
                INSERT INTO relation_edges (id, source_id, target_id, relation_type, weight, schema_source, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_id, target_id, relation_type) DO UPDATE SET
                    id=excluded.id,
                    weight=excluded.weight,
                    schema_source=excluded.schema_source
                """,
                (
                    edge.id,
                    edge.source_id,
                    edge.target_id,
                    edge.relation_type,
                    edge.weight,
                    edge.schema_source.value,
                    edge.created_at,
                ),
            )
            if not self._in_outer_transaction:
                self._conn.commit()

    def get_relation_edges(self, node_id: str) -> list[RelationEdge]:
        rows = self._conn.execute(
            """
            SELECT * FROM relation_edges
            WHERE source_id = ? OR target_id = ?
            ORDER BY created_at
            """,
            (node_id, node_id),
        ).fetchall()
        return [self._row_to_relation_edge(row) for row in rows]

    # ── Trace 边（联想投影） ───────────────────────────────

    def upsert_trace_edge(self, edge: TraceEdge) -> None:
        with self._write_lock:
            self._conn.execute(
                """
                INSERT INTO trace_edges (id, source_concept_id, target_concept_id, weight, valence, perspective, last_activated_at, decay_factor, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_concept_id, target_concept_id, perspective) DO UPDATE SET
                    id=excluded.id,
                    weight=excluded.weight,
                    valence=excluded.valence,
                    last_activated_at=excluded.last_activated_at,
                    decay_factor=excluded.decay_factor
                """,
                (
                    edge.id,
                    edge.source_concept_id,
                    edge.target_concept_id,
                    edge.weight,
                    edge.valence,
                    edge.perspective,
                    edge.last_activated_at,
                    edge.decay_factor,
                    edge.created_at,
                ),
            )
            if not self._in_outer_transaction:
                self._conn.commit()
            # R07：同步内存邻接索引（先移除同键旧条目，避免 UPSERT 重复追加）
            # CX-P1-E2：双向索引——source 与 target 两侧都登记（observe 写入无序共现对）
            for node_id in (edge.source_concept_id, edge.target_concept_id):
                self._remove_index_entry(node_id, edge, edge.perspective)
                self._adjacency_index.setdefault(node_id, []).append(edge)

    def _remove_index_entry(
        self, node_id: str, edge: TraceEdge, perspective: str,
    ) -> None:
        """移除 node_id 邻接列表中与 edge 同键的旧条目（UPSERT 覆盖不重复）。"""
        edges = self._adjacency_index.get(node_id)
        if not edges:
            return
        self._adjacency_index[node_id] = [
            e for e in edges
            if not (
                e.source_concept_id == edge.source_concept_id
                and e.target_concept_id == edge.target_concept_id
                and e.perspective == perspective
            )
        ]

    def get_trace_edges(self, node_id: str) -> list[TraceEdge]:
        rows = self._conn.execute(
            """
            SELECT * FROM trace_edges
            WHERE source_concept_id = ? OR target_concept_id = ?
            ORDER BY last_activated_at DESC
            """,
            (node_id, node_id),
        ).fetchall()
        return [self._row_to_trace_edge(row) for row in rows]

    def get_adjacent_traces(self, concept_id: str, agent_id: str = "") -> list[TraceEdge]:
        """R07：优先读内存邻接索引。

        Args:
            concept_id: 源概念 id
            agent_id: 非空时按视角过滤（perspective 以 "agent:{agent_id}" 开头）
        """
        edges = self._adjacency_index.get(concept_id, [])
        if not agent_id:
            return list(edges)
        prefix = f"agent:{agent_id}"
        return [e for e in edges if e.perspective.startswith(prefix)]

    # ── 批量衰减 ──────────────────────────────────────────

    def decay_relation_edges(self, factor: float) -> int:
        """关系边权重批量衰减（下限 0.05）。"""
        with self._write_lock:
            cursor = self._conn.execute(
                """
                UPDATE relation_edges
                SET weight = MAX(0.05, weight * ?)
                """,
                (max(0.0, min(1.0, factor)),),
            )
            self._conn.commit()
            return cursor.rowcount

    def decay_trace_edges(self, factor: float) -> int:
        """Trace 边 decay_factor 批量衰减（下限 0.05）。"""
        with self._write_lock:
            cursor = self._conn.execute(
                """
                UPDATE trace_edges
                SET decay_factor = MAX(0.05, decay_factor * ?)
                """,
                (max(0.0, min(1.0, factor)),),
            )
            self._conn.commit()
            return cursor.rowcount

    def decay_all(self, *, relation_factor: float, trace_factor: float) -> DecayResult:
        """关系边与 Trace 边统一衰减（FusedDecayEngine 委托）。"""
        with self._write_lock:
            relation_affected = self._conn.execute(
                """
                UPDATE relation_edges
                SET weight = MAX(0.05, weight * ?)
                """,
                (max(0.0, min(1.0, relation_factor)),),
            ).rowcount
            trace_affected = self._conn.execute(
                """
                UPDATE trace_edges
                SET decay_factor = MAX(0.05, decay_factor * ?)
                """,
                (max(0.0, min(1.0, trace_factor)),),
            ).rowcount
            self._conn.commit()
            self._rebuild_adjacency_index()
            return DecayResult(
                relation_affected=relation_affected,
                trace_affected=trace_affected,
            )

    def close(self) -> None:
        self._conn.close()

    # ── 行转换 ────────────────────────────────────────────

    @staticmethod
    def _row_to_node(row: sqlite3.Row) -> ConceptNode:
        return ConceptNode(
            id=row["id"],
            name=row["name"],
            type=NodeCategory(row["type"]),
            embedding=row["embedding"],
            embedding_pending=bool(row["embedding_pending"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _row_to_relation_edge(row: sqlite3.Row) -> RelationEdge:
        return RelationEdge(
            id=row["id"],
            source_id=row["source_id"],
            target_id=row["target_id"],
            relation_type=row["relation_type"],
            weight=row["weight"],
            schema_source=EdgeSource(row["schema_source"]),
            created_at=row["created_at"],
        )

    @staticmethod
    def _row_to_trace_edge(row: sqlite3.Row) -> TraceEdge:
        return TraceEdge(
            id=row["id"],
            source_concept_id=row["source_concept_id"],
            target_concept_id=row["target_concept_id"],
            weight=row["weight"],
            valence=row["valence"],
            perspective=row["perspective"],
            last_activated_at=row["last_activated_at"],
            decay_factor=row["decay_factor"],
            created_at=row["created_at"],
        )


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS concept_nodes (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK(type IN ('concept', 'entity', 'both')),
    embedding BLOB,
    embedding_pending INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS relation_edges (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES concept_nodes(id),
    target_id TEXT NOT NULL REFERENCES concept_nodes(id),
    relation_type TEXT NOT NULL,
    weight REAL NOT NULL DEFAULT 1.0,
    schema_source TEXT NOT NULL DEFAULT 'taxonomy_projection',
    created_at REAL NOT NULL,
    UNIQUE(source_id, target_id, relation_type)
);

CREATE TABLE IF NOT EXISTS trace_edges (
    id TEXT PRIMARY KEY,
    source_concept_id TEXT NOT NULL REFERENCES concept_nodes(id),
    target_concept_id TEXT NOT NULL REFERENCES concept_nodes(id),
    weight REAL NOT NULL DEFAULT 0.5,
    valence REAL NOT NULL DEFAULT 0.0,
    perspective TEXT NOT NULL DEFAULT '',
    last_activated_at REAL NOT NULL,
    decay_factor REAL NOT NULL DEFAULT 1.0,
    created_at REAL NOT NULL,
    UNIQUE(source_concept_id, target_concept_id, perspective)
);

CREATE INDEX IF NOT EXISTS idx_relation_source ON relation_edges(source_id);
CREATE INDEX IF NOT EXISTS idx_relation_target ON relation_edges(target_id);
CREATE INDEX IF NOT EXISTS idx_trace_source ON trace_edges(source_concept_id);
CREATE INDEX IF NOT EXISTS idx_trace_target ON trace_edges(target_concept_id);

CREATE TABLE IF NOT EXISTS event_writes (
    event_id TEXT PRIMARY KEY,
    written_at REAL NOT NULL
);
"""
