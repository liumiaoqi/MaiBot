from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path
from typing import Iterator

from src.common.logger import get_logger

from .enums import TimeOfDay, Valence
from .models import Trace

logger = get_logger("TraceStore")

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS traces (
    source TEXT NOT NULL,
    target TEXT NOT NULL,
    weight REAL NOT NULL,
    valence TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    timestamp REAL NOT NULL,
    detail_level REAL NOT NULL,
    time_of_day TEXT NOT NULL,
    observation_id TEXT NOT NULL,
    voice_name TEXT NOT NULL,
    PRIMARY KEY (source, target, agent_id, voice_name)
)
"""

_UPSERT_SQL = """
INSERT INTO traces (source, target, weight, valence, agent_id, timestamp, detail_level, time_of_day, observation_id, voice_name)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(source, target, agent_id, voice_name)
DO UPDATE SET weight=excluded.weight, valence=excluded.valence, timestamp=excluded.timestamp,
              detail_level=excluded.detail_level, time_of_day=excluded.time_of_day,
              observation_id=excluded.observation_id
"""

_DELETE_SQL = "DELETE FROM traces WHERE source=? AND target=? AND agent_id=? AND voice_name=?"

_QUERY_BY_CONCEPT_SQL = "SELECT * FROM traces WHERE source=? OR target=?"

_QUERY_BY_AGENT_SQL = "SELECT * FROM traces WHERE agent_id=?"

_COUNT_SQL = "SELECT COUNT(*) FROM traces"

_COUNT_BY_AGENT_SQL = "SELECT agent_id, COUNT(*) FROM traces GROUP BY agent_id"


def _row_to_trace(row: tuple) -> Trace:
    return Trace(
        source=row[0],
        target=row[1],
        weight=row[2],
        valence=Valence(row[3]),
        agent_id=row[4],
        timestamp=row[5],
        detail_level=row[6],
        time_of_day=TimeOfDay(row[7]),
        observation_id=row[8],
        voice_name=row[9],
    )


class TraceStore:
    """Trace 持久化存储（SQLite）+ 内存邻接索引"""

    def __init__(self, data_dir: Path) -> None:
        self._db_path = data_dir / "connectionist" / "traces.db"
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._adjacency: dict[str, dict[str, list[Trace]]] = {}
        self._all_traces: dict[tuple[str, str, str, str], Trace] = {}
        self._lock = asyncio.Lock()
        self._dirty = False
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(_CREATE_TABLE_SQL)
            conn.commit()
        self._load_from_db()

    def _load_from_db(self) -> None:
        self._adjacency.clear()
        self._all_traces.clear()
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute("SELECT * FROM traces").fetchall()
        for row in rows:
            trace = _row_to_trace(row)
            self._index_trace(trace)

    def _index_trace(self, trace: Trace) -> None:
        self._all_traces[trace.unique_key] = trace
        for concept in (trace.source, trace.target):
            by_agent = self._adjacency.setdefault(concept, {})
            traces = by_agent.setdefault(trace.agent_id, [])
            existing_keys = {t.unique_key for t in traces}
            if trace.unique_key not in existing_keys:
                traces.append(trace)

    def _deindex_trace(self, key: tuple[str, str, str, str]) -> None:
        old = self._all_traces.pop(key, None)
        if old is None:
            return
        for concept in (old.source, old.target):
            by_agent = self._adjacency.get(concept)
            if by_agent is None:
                continue
            traces = by_agent.get(old.agent_id)
            if traces is None:
                continue
            traces[:] = [t for t in traces if t.unique_key != key]
            if not traces:
                by_agent.pop(old.agent_id, None)
            if not by_agent:
                self._adjacency.pop(concept, None)

    async def create_trace(self, trace: Trace) -> None:
        async with self._lock:
            self._deindex_trace(trace.unique_key)
            self._index_trace(trace)
            self._persist_upsert(trace)
            self._dirty = True

    async def update_trace(self, trace: Trace) -> None:
        async with self._lock:
            self._deindex_trace(trace.unique_key)
            self._index_trace(trace)
            self._persist_upsert(trace)
            self._dirty = True

    async def delete_trace(self, key: tuple[str, str, str, str]) -> None:
        async with self._lock:
            self._deindex_trace(key)
            self._persist_delete(key)
            self._dirty = True

    def get_trace(self, key: tuple[str, str, str, str]) -> Trace | None:
        return self._all_traces.get(key)

    def query_by_concept(self, concept: str) -> list[Trace]:
        result: list[Trace] = []
        by_agent = self._adjacency.get(concept, {})
        for traces in by_agent.values():
            result.extend(traces)
        return result

    def query_by_concept_and_agent(self, concept: str, agent_id: str) -> list[Trace]:
        by_agent = self._adjacency.get(concept, {})
        return list(by_agent.get(agent_id, []))

    def query_by_agent(self, agent_id: str) -> list[Trace]:
        return [t for t in self._all_traces.values() if t.agent_id == agent_id]

    def query_by_observation_id(self, observation_id: str) -> list[Trace]:
        """按单个观察批次 ID 查询 Trace"""
        return [t for t in self._all_traces.values() if t.observation_id == observation_id]

    def query_by_observation_ids(self, observation_ids: list[str]) -> dict[str, list[Trace]]:
        """批量按观察批次 ID 查询 Trace，返回 observation_id → Trace 列表的映射"""
        obs_set = set(observation_ids)
        result: dict[str, list[Trace]] = {oid: [] for oid in obs_set}
        for t in self._all_traces.values():
            if t.observation_id in obs_set:
                result[t.observation_id].append(t)
        return result

    def get_adjacent_concepts(self, concept: str, agent_id: str) -> list[Trace]:
        return self.query_by_concept_and_agent(concept, agent_id)

    def all_traces(self) -> Iterator[Trace]:
        return iter(self._all_traces.values())

    def trace_count(self) -> int:
        return len(self._all_traces)

    def trace_count_by_agent(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for t in self._all_traces.values():
            counts[t.agent_id] = counts.get(t.agent_id, 0) + 1
        return counts

    def concept_count(self) -> int:
        return len(self._adjacency)

    async def flush(self) -> None:
        if not self._dirty:
            return
        self._dirty = False

    def _persist_upsert(self, trace: Trace) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                _UPSERT_SQL,
                (
                    trace.source,
                    trace.target,
                    trace.weight,
                    trace.valence.value,
                    trace.agent_id,
                    trace.timestamp,
                    trace.detail_level,
                    trace.time_of_day.value,
                    trace.observation_id,
                    trace.voice_name,
                ),
            )
            conn.commit()

    def _persist_delete(self, key: tuple[str, str, str, str]) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(_DELETE_SQL, key)
            conn.commit()

    async def batch_upsert(self, traces: list[Trace]) -> None:
        async with self._lock:
            for trace in traces:
                self._deindex_trace(trace.unique_key)
                self._index_trace(trace)
            with sqlite3.connect(self._db_path) as conn:
                conn.executemany(
                    _UPSERT_SQL,
                    [
                        (
                            t.source,
                            t.target,
                            t.weight,
                            t.valence.value,
                            t.agent_id,
                            t.timestamp,
                            t.detail_level,
                            t.time_of_day.value,
                            t.observation_id,
                            t.voice_name,
                        )
                        for t in traces
                    ],
                )
                conn.commit()
            self._dirty = True