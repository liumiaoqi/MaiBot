from __future__ import annotations

from typing import Any

from src.common.logger import get_logger

from ..connectionist.concept_index import ConceptIndex
from ..connectionist.enums import TimeOfDay, Valence
from ..connectionist.models import ExtractionResult, Trace
from ..connectionist.models import _time_of_day_from_timestamp
from ..connectionist.trace_store import TraceStore
from ..extraction.llm_concept_extractor import LLMConceptExtractor
from ..extraction.semantic_concept_extractor import SemanticConceptExtractor

logger = get_logger("DataConverter")


class DataConverter:
    """旧数据 -> Trace 转换器（LLM 增强版）"""

    def __init__(
        self,
        trace_store: TraceStore,
        concept_index: ConceptIndex,
        llm_extractor: LLMConceptExtractor | None = None,
    ) -> None:
        self._trace_store = trace_store
        self._concept_index = concept_index
        self._llm_extractor = llm_extractor
        self._semantic_extractor = SemanticConceptExtractor(concept_index) if concept_index else None

    async def convert_paragraph(self, paragraph: dict, agent_id: str = "") -> list[Trace]:
        text = paragraph.get("content", "")
        if not text:
            return []
        ts = self._parse_timestamp(paragraph)
        observation_id = f"migrated_p_{paragraph.get('hash', 'unknown')}"
        return await self._extract_and_create_traces(text, ts, observation_id, agent_id)

    async def convert_entity(self, entity: dict) -> None:
        name = entity.get("name", "")
        if not name:
            return
        entity_type = entity.get("type", "unknown")
        self._concept_index.register_concept(name, entity_type)

    async def convert_relation(self, relation: dict, agent_id: str = "") -> list[Trace]:
        subject = relation.get("subject", "")
        obj = relation.get("object", "")
        if not subject or not obj:
            return []
        strength = relation.get("strength", 0.5)
        if isinstance(strength, str):
            try:
                strength = float(strength)
            except (ValueError, TypeError):
                strength = 0.5
        weight = min(1.0, max(0.0, strength))
        ts = self._parse_timestamp(relation)
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
        return [trace]

    async def convert_episode(self, episode: dict, agent_id: str = "") -> list[Trace]:
        content = episode.get("content", "")
        if not content:
            return []
        ts = self._parse_timestamp(episode)
        observation_id = f"migrated_e_{episode.get('hash', 'unknown')}"
        return await self._extract_and_create_traces(content, ts, observation_id, agent_id)

    async def _extract_and_create_traces(
        self, text: str, ts: float, observation_id: str, agent_id: str
    ) -> list[Trace]:
        extraction = await self._try_extract(text)
        if not extraction or not extraction.concepts:
            return []

        concepts = extraction.concepts
        valence = extraction.valence
        traces: list[Trace] = []

        if extraction.relations:
            for rel in extraction.relations:
                if rel.source and rel.target and rel.source != rel.target:
                    trace = Trace(
                        source=rel.source,
                        target=rel.target,
                        weight=0.5,
                        valence=valence,
                        agent_id=agent_id,
                        timestamp=float(ts),
                        detail_level=0.3,
                        time_of_day=_time_of_day_from_timestamp(float(ts)) if ts else TimeOfDay.UNKNOWN,
                        observation_id=observation_id,
                        voice_name="migration",
                    )
                    await self._trace_store.create_trace(trace)
                    self._concept_index.register_concept(rel.source, "unknown")
                    self._concept_index.register_concept(rel.target, "unknown")
                    traces.append(trace)

        if not traces and len(concepts) >= 2:
            for i in range(len(concepts) - 1):
                src = concepts[i].name
                tgt = concepts[i + 1].name
                if src != tgt:
                    trace = Trace(
                        source=src,
                        target=tgt,
                        weight=0.4,
                        valence=valence,
                        agent_id=agent_id,
                        timestamp=float(ts),
                        detail_level=0.3,
                        time_of_day=_time_of_day_from_timestamp(float(ts)) if ts else TimeOfDay.UNKNOWN,
                        observation_id=observation_id,
                        voice_name="migration",
                    )
                    await self._trace_store.create_trace(trace)
                    self._concept_index.register_concept(src, concepts[i].concept_type)
                    self._concept_index.register_concept(tgt, concepts[i + 1].concept_type)
                    traces.append(trace)

        return traces

    async def _try_extract(self, text: str) -> ExtractionResult | None:
        if self._llm_extractor:
            try:
                result = await self._llm_extractor.extract(text)
                if result.concepts:
                    return result
            except Exception as e:
                logger.warning(f"LLM 提取失败，降级到 jieba: {e}")

        if self._semantic_extractor:
            try:
                result = await self._semantic_extractor.extract(text)
                if result.concepts:
                    return result
            except Exception as e:
                logger.warning(f"jieba 降级提取也失败: {e}")

        return None

    @staticmethod
    def _parse_timestamp(data: dict) -> float:
        ts = data.get("timestamp") or data.get("created_at") or data.get("start_time") or 0.0
        if isinstance(ts, str):
            try:
                from datetime import datetime
                ts = datetime.fromisoformat(ts).timestamp()
            except (ValueError, TypeError):
                ts = 0.0
        return float(ts)
