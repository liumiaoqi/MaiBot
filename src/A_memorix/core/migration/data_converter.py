from __future__ import annotations

from typing import Any

from src.common.logger import get_logger

from ..connectionist.concept_index import ConceptIndex
from ..connectionist.enums import TimeOfDay, Valence
from ..connectionist.models import Trace
from ..connectionist.models import _time_of_day_from_timestamp
from ..connectionist.trace_store import TraceStore

logger = get_logger("DataConverter")


class DataConverter:
    """旧数据 -> Trace 转换器"""

    def __init__(self, trace_store: TraceStore, concept_index: ConceptIndex) -> None:
        self._trace_store = trace_store
        self._concept_index = concept_index

    async def convert_paragraph(self, paragraph: dict, agent_id: str = "") -> Trace | None:
        text = paragraph.get("content", "")
        if not text:
            return None
        ts = paragraph.get("timestamp") or paragraph.get("created_at") or 0.0
        if isinstance(ts, str):
            try:
                from datetime import datetime
                ts = datetime.fromisoformat(ts).timestamp()
            except (ValueError, TypeError):
                ts = 0.0
        trace = Trace(
            source=text[:50],
            target=text[:50],
            weight=0.5,
            valence=Valence.NEUTRAL,
            agent_id=agent_id,
            timestamp=float(ts),
            detail_level=0.3,
            time_of_day=_time_of_day_from_timestamp(float(ts)) if ts else TimeOfDay.UNKNOWN,
            observation_id=f"migrated_p_{paragraph.get('hash', 'unknown')}",
            voice_name="migration",
        )
        await self._trace_store.create_trace(trace)
        return trace

    async def convert_entity(self, entity: dict) -> None:
        name = entity.get("name", "")
        if not name:
            return
        entity_type = entity.get("type", "unknown")
        self._concept_index.register_concept(name, entity_type)

    async def convert_relation(self, relation: dict, agent_id: str = "") -> Trace | None:
        subject = relation.get("subject", "")
        obj = relation.get("object", "")
        if not subject or not obj:
            return None
        strength = relation.get("strength", 0.5)
        if isinstance(strength, str):
            try:
                strength = float(strength)
            except (ValueError, TypeError):
                strength = 0.5
        weight = min(1.0, max(0.0, strength))
        ts = relation.get("timestamp") or relation.get("created_at") or 0.0
        if isinstance(ts, str):
            try:
                from datetime import datetime
                ts = datetime.fromisoformat(ts).timestamp()
            except (ValueError, TypeError):
                ts = 0.0
        trace = Trace(
            source=subject,
            target=obj,
            weight=weight,
            valence=Valence.NEUTRAL,
            agent_id=agent_id,
            timestamp=float(ts),
            detail_level=0.3,
            time_of_day=_time_of_day_from_timestamp(float(ts)) if ts else TimeOfDay.UNKNOWN,
            observation_id=f"migrated_r_{relation.get('hash', 'unknown')}",
            voice_name="migration",
        )
        await self._trace_store.create_trace(trace)
        self._concept_index.register_concept(subject, "unknown")
        self._concept_index.register_concept(obj, "unknown")
        return trace

    async def convert_episode(self, episode: dict, agent_id: str = "") -> Trace | None:
        content = episode.get("content", "")
        if not content:
            return None
        ts = episode.get("timestamp") or episode.get("start_time") or 0.0
        if isinstance(ts, str):
            try:
                from datetime import datetime
                ts = datetime.fromisoformat(ts).timestamp()
            except (ValueError, TypeError):
                ts = 0.0
        trace = Trace(
            source=content[:50],
            target=content[:50],
            weight=0.5,
            valence=Valence.NEUTRAL,
            agent_id=agent_id,
            timestamp=float(ts),
            detail_level=0.3,
            time_of_day=_time_of_day_from_timestamp(float(ts)) if ts else TimeOfDay.UNKNOWN,
            observation_id=f"migrated_e_{episode.get('hash', 'unknown')}",
            voice_name="migration",
        )
        await self._trace_store.create_trace(trace)
        return trace