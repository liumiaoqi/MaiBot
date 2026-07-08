from __future__ import annotations

from pathlib import Path

from src.common.logger import get_logger

from .concept_index import ConceptIndex
from .enums import Valence
from .granular_decay_engine import GranularDecayEngine
from .models import DecayResult, MemoryPersonalityV2, InnerVoice, ObserveResult, ProfileView, RecallItem, ReflectResult
from .observer import Observer
from .profile_deriver import ProfileDeriver
from .salience_evaluator import SalienceEvaluator
from .spreading_activation import SpreadingActivation
from .trace_store import TraceStore
from ..extraction.llm_concept_extractor import LLMConceptExtractor
from ..personality.inner_voice_processor import InnerVoiceProcessor
from ..personality.personality_registry import PersonalityRegistry

logger = get_logger("MemoryField")


class MemoryField:
    """连接主义记忆系统核心运行时"""

    def __init__(self, data_dir: Path) -> None:
        self._trace_store = TraceStore(data_dir)
        self._concept_index = ConceptIndex(data_dir)
        self._personality_registry = PersonalityRegistry()
        self._llm_extractor = LLMConceptExtractor()
        self._salience_evaluator = SalienceEvaluator()
        self._voice_processor = InnerVoiceProcessor()
        self._spreading_activation = SpreadingActivation(self._trace_store, self._concept_index)
        self._profile_deriver = ProfileDeriver(self._trace_store, self._personality_registry)
        self._granular_decay_engine = GranularDecayEngine(self._trace_store, self._personality_registry)
        self._observer = Observer(
            trace_store=self._trace_store,
            concept_index=self._concept_index,
            personality_registry=self._personality_registry,
            llm_extractor=self._llm_extractor,
            salience_evaluator=self._salience_evaluator,
            voice_processor=self._voice_processor,
        )

    async def observe(
        self,
        text: str,
        valence: Valence = Valence.NEUTRAL,
        timestamp: float | None = None,
        source_id: str = "",
        session_id: str = "",
    ) -> ObserveResult:
        return await self._observer.observe(text, valence, timestamp, source_id, session_id)

    def recall(
        self,
        seeds: list[str],
        agent_id: str,
        min_weight: float = 0.05,
        max_results: int = 20,
    ) -> list[RecallItem]:
        personality = self._personality_registry.get_personality(agent_id)
        return self._spreading_activation.recall(seeds, agent_id, personality, min_weight, max_results)

    async def derive_profile(self, subject: str, observer: str, now: float | None = None) -> ProfileView:
        return await self._profile_deriver.derive_profile(subject, observer, now)

    async def reflect(self, subject: str, agent_id: str) -> ReflectResult:
        return await self._profile_deriver.reflect(subject, agent_id)

    async def granular_decay(self, elapsed_hours: float = 1.0) -> DecayResult:
        return await self._granular_decay_engine.granular_decay(elapsed_hours)

    def register_agent(self, agent_id: str, personality: MemoryPersonalityV2, voices: list[InnerVoice]) -> None:
        self._personality_registry.register_agent(agent_id, personality, voices)

    def memory_stats(self) -> dict:
        return {
            "trace_count": self._trace_store.trace_count(),
            "concept_count": self._concept_index.concept_count(),
            "agent_stats": self._trace_store.trace_count_by_agent(),
            "registered_agents": self._personality_registry.registered_agents(),
        }