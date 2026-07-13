from __future__ import annotations

import time
from typing import Any

from ..connectionist.enums import Valence
from ..connectionist.models import (
    AssociationItem,
    ContradictionItem,
    ProfileView,
    ReflectResult,
    TimelineItem,
    VoiceView,
    _relative_time_from_timestamp,
)
from ..connectionist.trace_store import TraceStore
from ..personality.personality_registry import PersonalityRegistry


class ProfileDeriver:
    """画像实时推导"""

    DEPTH_THRESHOLDS = [(3, "初识"), (8, "相识"), (15, "熟悉")]

    def __init__(self, trace_store: TraceStore, personality_registry: PersonalityRegistry) -> None:
        self._trace_store = trace_store
        self._personality_registry = personality_registry
        self._cognitive_stratifier = None
        self._episode_store = None

    def inject_narrative_deps(self, cognitive_stratifier: Any, episode_store: Any) -> None:
        """注入叙事原型依赖（由 MemoryField 在初始化后调用）"""
        self._cognitive_stratifier = cognitive_stratifier
        self._episode_store = episode_store

    async def derive_profile(self, subject: str, observer: str, now: float | None = None) -> ProfileView:
        now = now or time.time()
        traces = self._trace_store.query_by_concept_and_agent(subject, observer)

        if not traces:
            return ProfileView(subject=subject, observer=observer, depth="空白")

        associations: list[AssociationItem] = []
        voices: dict[str, list[VoiceView]] = {}
        timeline: list[TimelineItem] = []
        concept_valence_by_voice: dict[str, dict[str, Valence]] = {}

        for trace in traces:
            other = trace.target if trace.source == subject else trace.source

            associations.append(
                AssociationItem(
                    concept=other,
                    strength=trace.weight,
                    valence=trace.valence,
                    voice=trace.voice_name,
                    time_of_day=trace.time_of_day,
                    relative_time=_relative_time_from_timestamp(trace.timestamp, now) if trace.timestamp > 0 else "",
                    detail=trace.detail_level,
                )
            )

            voice_views = voices.setdefault(trace.voice_name, [])
            voice_views.append(VoiceView(concept=other, valence=trace.valence, strength=trace.weight))

            timeline.append(
                TimelineItem(
                    timestamp=trace.timestamp,
                    concept=other,
                    valence=trace.valence,
                    voice=trace.voice_name,
                    detail_level=trace.detail_level,
                )
            )

            cv = concept_valence_by_voice.setdefault(trace.voice_name, {})
            cv[other] = trace.valence

        associations.sort(key=lambda a: -a.strength)
        associations = associations[:20]
        timeline.sort(key=lambda t: t.timestamp)

        contradictions = self._find_contradictions(concept_valence_by_voice)

        depth = "深知"
        for threshold, label in self.DEPTH_THRESHOLDS:
            if len(traces) <= threshold:
                depth = label
                break

        concept_type = "unknown"
        cognitive_type = ""
        episodes: list = []
        sagas: list = []

        if self._cognitive_stratifier is not None:
            cog_entries = self._cognitive_stratifier.get_cognitive_entries(observer, subject)
            if cog_entries:
                cognitive_type = cog_entries[0].type

        if self._episode_store is not None:
            for ep in self._episode_store.query_episodes_by_agent(observer, status="active"):
                if subject in ep.all_concepts:
                    episodes.append({"id": ep.id, "title": ep.title, "emotional_axis": ep.emotional_axis})
            for saga in self._episode_store.query_sagas_by_agent(observer, status="active"):
                sagas.append({"id": saga.id, "title": saga.title, "emotional_axis": saga.emotional_axis})

        return ProfileView(
            subject=subject,
            observer=observer,
            associations=associations,
            voices=voices,
            contradictions=contradictions[:10],
            timeline=timeline,
            depth=depth,
            concept_type=concept_type,
            cognitive_type=cognitive_type,
            episodes=episodes,
            sagas=sagas,
        )

    async def reflect(self, subject: str, agent_id: str) -> ReflectResult:
        traces = self._trace_store.query_by_concept_and_agent(subject, agent_id)
        if not traces:
            return ReflectResult(subject=subject, agent_id=agent_id)

        voices: dict[str, list[VoiceView]] = {}
        concept_valence_by_voice: dict[str, dict[str, Valence]] = {}

        for trace in traces:
            other = trace.target if trace.source == subject else trace.source
            voice_views = voices.setdefault(trace.voice_name, [])
            voice_views.append(VoiceView(concept=other, valence=trace.valence, strength=trace.weight))
            cv = concept_valence_by_voice.setdefault(trace.voice_name, {})
            cv[other] = trace.valence

        contradictions = self._find_contradictions(concept_valence_by_voice)

        return ReflectResult(
            subject=subject,
            agent_id=agent_id,
            voices=voices,
            contradictions=contradictions[:10],
        )

    def _find_contradictions(self, concept_valence_by_voice: dict[str, dict[str, Valence]]) -> list[ContradictionItem]:
        contradictions: list[ContradictionItem] = []
        all_concepts: set[str] = set()
        for cv in concept_valence_by_voice.values():
            all_concepts |= set(cv.keys())

        voice_names = list(concept_valence_by_voice.keys())
        for concept in all_concepts:
            for i in range(len(voice_names)):
                for j in range(i + 1, len(voice_names)):
                    va = concept_valence_by_voice[voice_names[i]].get(concept)
                    vb = concept_valence_by_voice[voice_names[j]].get(concept)
                    if va and vb and va != vb:
                        contradictions.append(
                            ContradictionItem(
                                concept=concept,
                                voice_a=voice_names[i],
                                valence_a=va,
                                voice_b=voice_names[j],
                                valence_b=vb,
                            )
                        )
        return contradictions