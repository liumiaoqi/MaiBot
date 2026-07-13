from __future__ import annotations

import time

from src.common.logger import get_logger

from ..connectionist.concept_index import ConceptIndex
from ..connectionist.enums import Valence
from ..connectionist.models import (
    AgentMemoryResult,
    ExtractionResult,
    InnerVoice,
    MemoryPersonalityV2,
    ObserveResult,
    Trace,
    _time_of_day_from_timestamp,
)
from ..connectionist.salience_evaluator import SalienceEvaluator
from ..connectionist.trace_store import TraceStore
from ..extraction.llm_concept_extractor import LLMConceptExtractor
from ..personality.inner_voice_processor import InnerVoiceProcessor
from ..personality.personality_registry import PersonalityRegistry

logger = get_logger("Observer")


class Observer:
    """消息观察与选择性记忆"""

    def __init__(
        self,
        trace_store: TraceStore,
        concept_index: ConceptIndex,
        personality_registry: PersonalityRegistry,
        llm_extractor: LLMConceptExtractor,
        salience_evaluator: SalienceEvaluator,
        voice_processor: InnerVoiceProcessor,
    ) -> None:
        self._trace_store = trace_store
        self._concept_index = concept_index
        self._personality_registry = personality_registry
        self._llm_extractor = llm_extractor
        self._salience_evaluator = salience_evaluator
        self._voice_processor = voice_processor
        self._obs_counter = 0

    async def observe(
        self,
        text: str,
        valence: Valence = Valence.NEUTRAL,
        timestamp: float | None = None,
        source_id: str = "",
        session_id: str = "",
    ) -> ObserveResult:
        timestamp = timestamp or time.time()

        extraction = await self._llm_extractor.extract(text)
        if not extraction.concepts:
            return ObserveResult(text=text, extraction=extraction)

        concept_names = [c.name for c in extraction.concepts]
        for c in extraction.concepts:
            self._concept_index.register_concept(c.name, c.concept_type)
            self._concept_index.increment_count(c.name)

        existing_concepts = frozenset(self._concept_index.all_concepts().keys())
        new_concepts = frozenset(concept_names) - existing_concepts

        memory_results: list[AgentMemoryResult] = []

        for agent_id in self._personality_registry.registered_agents():
            personality = self._personality_registry.get_personality(agent_id)
            score, reason = self._salience_evaluator.evaluate(
                concepts=concept_names,
                agent_id=agent_id,
                valence=extraction.valence,
                personality=personality,
                existing_concepts=existing_concepts,
                new_concepts=new_concepts,
            )

            threshold = 0.25 / max(0.5, personality.curiosity)

            if score < threshold:
                memory_results.append(
                    AgentMemoryResult(agent_id=agent_id, remembered=False, reason=f"显著性不足: {reason}")
                )
                continue

            voices = self._personality_registry.get_voices(agent_id)
            traces_created = 0
            voices_active: list[str] = []

            self._obs_counter += 1
            obs_id = f"obs_{self._obs_counter}"

            for voice in voices:
                transformed_valence, filtered_concepts = self._voice_processor.process_experience(
                    valence=extraction.valence,
                    concepts=concept_names,
                    voice=voice,
                    existing=frozenset(self._concept_index.all_concepts().keys()),
                )

                if len(filtered_concepts) < 2:
                    continue

                voices_active.append(voice.name)

                for i in range(len(filtered_concepts)):
                    for j in range(i + 1, len(filtered_concepts)):
                        source = filtered_concepts[i]
                        target = filtered_concepts[j]

                        existing_trace = self._trace_store.get_trace(
                            (source, target, agent_id, voice.name)
                        )

                        if existing_trace is not None:
                            existing_trace.weight = min(1.0, existing_trace.weight + personality.reinforcement_boost)
                            existing_trace.detail_level = min(1.0, existing_trace.detail_level + 0.3)
                            existing_trace.timestamp = timestamp
                            existing_trace.observation_id = obs_id
                            await self._trace_store.update_trace(existing_trace)
                        else:
                            trace = Trace(
                                source=source,
                                target=target,
                                weight=0.5 * voice.weight_multiplier,
                                valence=transformed_valence,
                                agent_id=agent_id,
                                timestamp=timestamp,
                                detail_level=1.0,
                                time_of_day=_time_of_day_from_timestamp(timestamp),
                                observation_id=obs_id,
                                voice_name=voice.name,
                            )
                            await self._trace_store.create_trace(trace)

                        traces_created += 1

            memory_results.append(
                AgentMemoryResult(
                    agent_id=agent_id,
                    remembered=True,
                    reason=reason,
                    traces_created=traces_created,
                    voices_active=voices_active,
                    observation_id=obs_id,
                )
            )

        return ObserveResult(
            text=text,
            extraction=extraction,
            memory_results=memory_results,

            concept_names=concept_names,
        )