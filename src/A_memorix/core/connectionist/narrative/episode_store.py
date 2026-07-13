from __future__ import annotations

import json
import sqlite3

from pathlib import Path

from src.common.logger import get_logger

from ..models import Episode, Saga

logger = get_logger("EpisodeStore")

_CREATE_EPISODES_SQL = """
CREATE TABLE IF NOT EXISTS episodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    weight REAL NOT NULL DEFAULT 0.5,
    emotional_axis TEXT NOT NULL DEFAULT 'none',
    fragment_ids TEXT NOT NULL,
    concept_bridge TEXT NOT NULL DEFAULT '[]',
    all_concepts TEXT NOT NULL DEFAULT '[]',
    consolidation_type TEXT NOT NULL DEFAULT 'standard',
    status TEXT NOT NULL DEFAULT 'active',
    detail_level REAL NOT NULL DEFAULT 1.0,
    last_accessed_at REAL NOT NULL DEFAULT 0.0,
    timestamp REAL NOT NULL DEFAULT 0.0
)
"""

_CREATE_SAGAS_SQL = """
CREATE TABLE IF NOT EXISTS sagas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    emotional_axis TEXT NOT NULL DEFAULT 'none',
    episode_ids TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    last_accessed_at REAL NOT NULL DEFAULT 0.0,
    timestamp REAL NOT NULL DEFAULT 0.0
)
"""

_CREATE_FRAGMENT_STATUS_SQL = """
CREATE TABLE IF NOT EXISTS fragment_status (
    observation_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    last_accessed_at REAL NOT NULL DEFAULT 0.0,
    PRIMARY KEY (observation_id, agent_id)
)
"""

_CREATE_INDEXES_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_episodes_agent ON episodes(agent_id)",
    "CREATE INDEX IF NOT EXISTS idx_episodes_status ON episodes(agent_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_sagas_agent ON sagas(agent_id)",
    "CREATE INDEX IF NOT EXISTS idx_sagas_status ON sagas(agent_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_fragment_status_state ON fragment_status(agent_id, status)",
]


class EpisodeStore:
    """Episode/Saga/FragmentStatus SQLite 持久化，使用 TraceStore 的数据库连接"""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(_CREATE_EPISODES_SQL)
            conn.execute(_CREATE_SAGAS_SQL)
            conn.execute(_CREATE_FRAGMENT_STATUS_SQL)
            for idx_sql in _CREATE_INDEXES_SQL:
                conn.execute(idx_sql)
            conn.commit()

    # ── Episode CRUD ──────────────────────────────────

    def insert_episode(self, episode: Episode) -> int:
        with sqlite3.connect(self._db_path) as conn:
            cursor = conn.execute(
                """INSERT INTO episodes (agent_id, title, content, weight, emotional_axis,
                   fragment_ids, concept_bridge, all_concepts, consolidation_type, status,
                   detail_level, last_accessed_at, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    episode.agent_id,
                    episode.title,
                    episode.content,
                    episode.weight,
                    episode.emotional_axis,
                    json.dumps(episode.fragment_ids),
                    json.dumps(episode.concept_bridge),
                    json.dumps(episode.all_concepts),
                    episode.consolidation_type,
                    episode.status,
                    episode.detail_level,
                    episode.last_accessed_at,
                    episode.timestamp,
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def query_episodes_by_agent(self, agent_id: str, status: str = "") -> list[Episode]:
        sql = "SELECT * FROM episodes WHERE agent_id=?"
        params: list = [agent_id]
        if status:
            sql += " AND status=?"
            params.append(status)
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_episode(row) for row in rows]

    def update_episode_status(self, episode_id: int, status: str) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "UPDATE episodes SET status=? WHERE id=?",
                (status, episode_id),
            )
            conn.commit()

    def _row_to_episode(self, row: tuple) -> Episode:
        return Episode(
            id=row[0],
            agent_id=row[1],
            title=row[2],
            content=row[3],
            weight=row[4],
            emotional_axis=row[5],
            fragment_ids=json.loads(row[6]),
            concept_bridge=json.loads(row[7]),
            all_concepts=json.loads(row[8]),
            consolidation_type=row[9],
            status=row[10],
            detail_level=row[11],
            last_accessed_at=row[12],
            timestamp=row[13],
        )

    # ── Saga CRUD ─────────────────────────────────────

    def insert_saga(self, saga: Saga) -> int:
        with sqlite3.connect(self._db_path) as conn:
            cursor = conn.execute(
                """INSERT INTO sagas (agent_id, title, description, emotional_axis,
                   episode_ids, status, last_accessed_at, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    saga.agent_id,
                    saga.title,
                    saga.description,
                    saga.emotional_axis,
                    json.dumps(saga.episode_ids),
                    saga.status,
                    saga.last_accessed_at,
                    saga.timestamp,
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def query_sagas_by_agent(self, agent_id: str, status: str = "") -> list[Saga]:
        sql = "SELECT * FROM sagas WHERE agent_id=?"
        params: list = [agent_id]
        if status:
            sql += " AND status=?"
            params.append(status)
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_saga(row) for row in rows]

    def update_saga_status(self, saga_id: int, status: str) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "UPDATE sagas SET status=? WHERE id=?",
                (status, saga_id),
            )
            conn.commit()

    def _row_to_saga(self, row: tuple) -> Saga:
        return Saga(
            id=row[0],
            agent_id=row[1],
            title=row[2],
            description=row[3],
            emotional_axis=row[4],
            episode_ids=json.loads(row[5]),
            status=row[6],
            last_accessed_at=row[7],
            timestamp=row[8],
        )

    # ── FragmentStatus CRUD ───────────────────────────

    def upsert_fragment_status(
        self, observation_id: str, agent_id: str, status: str = "active"
    ) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """INSERT INTO fragment_status (observation_id, agent_id, status, last_accessed_at)
                   VALUES (?, ?, ?, 0.0)
                   ON CONFLICT(observation_id, agent_id)
                   DO UPDATE SET status=excluded.status""",
                (observation_id, agent_id, status),
            )
            conn.commit()

    def query_fragments_status(self, agent_id: str = "") -> list[dict]:
        sql = "SELECT observation_id, agent_id, status, last_accessed_at FROM fragment_status"
        params: list = []
        if agent_id:
            sql += " WHERE agent_id=?"
            params.append(agent_id)
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(sql, params).fetchall()
        return [
            {
                "observation_id": row[0],
                "agent_id": row[1],
                "status": row[2],
                "last_accessed_at": row[3],
            }
            for row in rows
        ]

    def query_unwoven_observation_ids(self, agent_id: str) -> list[str]:
        """查询未编织的 observation_id（有 fragment_status 但未被任何 Episode 引用）"""
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT observation_id FROM fragment_status WHERE agent_id=? AND status='active'",
                (agent_id,),
            ).fetchall()
        all_obs_ids = {row[0] for row in rows}

        # 排除已被 Episode 引用的
        episode_rows = conn.execute(
            "SELECT fragment_ids FROM episodes WHERE agent_id=?",
            (agent_id,),
        ).fetchall()
        woven_obs_ids: set[str] = set()
        for row in episode_rows:
            woven_obs_ids.update(json.loads(row[0]))

        return sorted(all_obs_ids - woven_obs_ids)

    def get_fragment_statuses_map(self, agent_id: str) -> dict[str, str]:
        """获取 observation_id → status 映射"""
        statuses = self.query_fragments_status(agent_id)
        return {s["observation_id"]: s["status"] for s in statuses}