from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from src.common.logger import get_logger

from ..models import CognitiveEntry

logger = get_logger("CognitiveStore")

_CREATE_ENTRIES_SQL = """
CREATE TABLE IF NOT EXISTS cognitive_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    concept TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    type TEXT NOT NULL,
    content TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0.3,
    decay_type TEXT NOT NULL DEFAULT 'evidence_dependent',
    evidence_count INTEGER NOT NULL DEFAULT 0,
    last_evidence_at REAL NOT NULL DEFAULT 0.0,
    source_diversity INTEGER NOT NULL DEFAULT 1,
    source_quality TEXT NOT NULL DEFAULT 'inferred',
    status TEXT NOT NULL DEFAULT 'active',
    tags TEXT NOT NULL DEFAULT '[]',
    expires_at REAL,
    evolution_history TEXT NOT NULL DEFAULT '[]',
    superseded_by INTEGER,
    contradicts_id INTEGER,
    observation_ids TEXT NOT NULL DEFAULT '[]',
    timestamp REAL NOT NULL DEFAULT 0.0
)
"""

_CREATE_STOPWORDS_SQL = """
CREATE TABLE IF NOT EXISTS intuition_stopwords (
    word TEXT PRIMARY KEY,
    frequency INTEGER NOT NULL DEFAULT 0,
    updated_at REAL NOT NULL DEFAULT 0.0
)
"""

_CREATE_INDEXES_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_cog_entry_concept ON cognitive_entries(concept, agent_id)",
    "CREATE INDEX IF NOT EXISTS idx_cog_entry_type ON cognitive_entries(agent_id, type, status)",
    "CREATE INDEX IF NOT EXISTS idx_cog_entry_status ON cognitive_entries(agent_id, status)",
]


class CognitiveStore:
    """CognitiveEntry + Stopwords SQLite 持久化"""

    def __init__(self, db_path: Path | str) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(_CREATE_ENTRIES_SQL)
            conn.execute(_CREATE_STOPWORDS_SQL)
            for idx_sql in _CREATE_INDEXES_SQL:
                conn.execute(idx_sql)
            conn.commit()

    # ── CognitiveEntry CRUD ───────────────────────────

    def insert_entry(self, entry: CognitiveEntry) -> int:
        with sqlite3.connect(self._db_path) as conn:
            cursor = conn.execute(
                """INSERT INTO cognitive_entries
                   (concept, agent_id, type, content, confidence, decay_type,
                    evidence_count, last_evidence_at, source_diversity, source_quality,
                    status, tags, expires_at, evolution_history, superseded_by,
                    contradicts_id, observation_ids, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    entry.concept,
                    entry.agent_id,
                    entry.type,
                    entry.content,
                    entry.confidence,
                    entry.decay_type,
                    entry.evidence_count,
                    entry.last_evidence_at,
                    entry.source_diversity,
                    entry.source_quality,
                    entry.status,
                    json.dumps(entry.tags),
                    entry.expires_at,
                    json.dumps(entry.evolution_history),
                    entry.superseded_by,
                    entry.contradicts_id,
                    json.dumps(entry.observation_ids),
                    entry.timestamp,
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def query_by_concept(self, concept: str, agent_id: str, status: str = "active") -> list[CognitiveEntry]:
        sql = "SELECT * FROM cognitive_entries WHERE concept=? AND agent_id=?"
        params: list = [concept, agent_id]
        if status:
            sql += " AND status=?"
            params.append(status)
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_entry(row) for row in rows]

    def query_by_type(self, agent_id: str, types: list[str], status: str = "active") -> list[CognitiveEntry]:
        if not types:
            return []
        placeholders = ",".join("?" * len(types))
        sql = f"SELECT * FROM cognitive_entries WHERE agent_id=? AND type IN ({placeholders})"
        params: list = [agent_id, *types]
        if status:
            sql += " AND status=?"
            params.append(status)
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_entry(row) for row in rows]

    def query_active_current_state(self, agent_id: str, limit: int = 12) -> list[CognitiveEntry]:
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM cognitive_entries WHERE agent_id=? AND type='current_state' AND status='active' ORDER BY timestamp DESC LIMIT ?",
                (agent_id, limit),
            ).fetchall()
        return [self._row_to_entry(row) for row in rows]

    def update_entry(self, entry_id: int, **kwargs) -> None:
        if not kwargs:
            return
        sets = ", ".join(f"{k}=?" for k in kwargs)
        values = list(kwargs.values()) + [entry_id]
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(f"UPDATE cognitive_entries SET {sets} WHERE id=?", values)
            conn.commit()

    def increment_evidence(
        self, entry_id: int, observation_id: str, confidence_delta: float
    ) -> None:
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT observation_ids, confidence, evidence_count FROM cognitive_entries WHERE id=?",
                (entry_id,),
            ).fetchone()
            if row is None:
                return
            obs_ids = json.loads(row[0])
            if observation_id not in obs_ids:
                obs_ids.append(observation_id)
            new_confidence = min(1.0, row[1] + confidence_delta)
            new_evidence = row[2] + 1
            conn.execute(
                "UPDATE cognitive_entries SET observation_ids=?, confidence=?, evidence_count=?, last_evidence_at=? WHERE id=?",
                (json.dumps(obs_ids), new_confidence, new_evidence, _now(), entry_id),
            )
            conn.commit()

    def count_active_by_type(self, agent_id: str, entry_type: str) -> int:
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM cognitive_entries WHERE agent_id=? AND type=? AND status='active'",
                (agent_id, entry_type),
            ).fetchone()
        return row[0] if row else 0

    def _row_to_entry(self, row: tuple) -> CognitiveEntry:
        return CognitiveEntry(
            id=row[0],
            concept=row[1],
            agent_id=row[2],
            type=row[3],
            content=row[4],
            confidence=row[5],
            decay_type=row[6],
            evidence_count=row[7],
            last_evidence_at=row[8],
            source_diversity=row[9],
            source_quality=row[10],
            status=row[11],
            tags=json.loads(row[12]),
            expires_at=row[13],
            evolution_history=json.loads(row[14]),
            superseded_by=row[15],
            contradicts_id=row[16],
            observation_ids=json.loads(row[17]),
            timestamp=row[18],
        )

    # ── Stopwords CRUD ────────────────────────────────

    def upsert_stopword(self, word: str, frequency: int) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """INSERT INTO intuition_stopwords (word, frequency, updated_at)
                   VALUES (?, ?, ?)
                   ON CONFLICT(word) DO UPDATE SET frequency=excluded.frequency, updated_at=excluded.updated_at""",
                (word, frequency, _now()),
            )
            conn.commit()

    def query_stopwords(self, min_frequency: int = 5) -> list[str]:
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT word FROM intuition_stopwords WHERE frequency >= ?",
                (min_frequency,),
            ).fetchall()
        return [row[0] for row in rows]

    def update_frequencies(self, concept_counts: dict[str, int]) -> None:
        for word, count in concept_counts.items():
            self.upsert_stopword(word, count)


def _now() -> float:
    import time
    return time.time()