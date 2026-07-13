from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from src.common.logger import get_logger

from .cognitive import CognitiveStratifier, CognitiveStore
from .concept_index import ConceptIndex
from .enums import Valence
from .granular_decay_engine import GranularDecayEngine
from .intuition import IntuitionEngine, StopwordManager
from .lifecycle import LifecycleManager
from .models import (
    CognitiveDecayResult,
    DecayResult,
    InnerVoice,
    LifecycleResult,
    MemoryPersonalityV2,
    ObserveResult,
    ProfileView,
    RecallItem,
    ReflectResult,
)
from .narrative import NarrativeWeaver
from .narrative.episode_store import EpisodeStore
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

    def __init__(self, data_dir: Path, *, llm_client: Any = None) -> None:
        self._trace_store = TraceStore(data_dir)
        self._concept_index = ConceptIndex(data_dir)
        self._personality_registry = PersonalityRegistry()
        self._llm_extractor = LLMConceptExtractor(llm_client=llm_client, concept_index=self._concept_index)
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

        # 叙事原型子模块
        db_path = data_dir / "connectionist.db"
        self._episode_store = EpisodeStore(db_path)
        self._cognitive_store = CognitiveStore(db_path)
        self._narrative_weaver = NarrativeWeaver(self._trace_store, self._episode_store, llm_client=llm_client)
        self._cognitive_stratifier = CognitiveStratifier(self._cognitive_store)
        self._lifecycle_manager = LifecycleManager(self._episode_store)
        self._stopword_manager = StopwordManager(self._cognitive_store)
        self._intuition_engine = IntuitionEngine(
            self._cognitive_stratifier, self._episode_store, self._stopword_manager,
        )

        # 注入叙事原型依赖到 ProfileDeriver
        self._profile_deriver.inject_narrative_deps(self._cognitive_stratifier, self._episode_store)

        # 迁移阶段守卫（可选，由外部注入）
        self._migration_adapter: Any = None

    def set_migration_adapter(self, adapter: Any) -> None:
        """注入迁移适配器（由 SDKMemoryKernel 初始化后调用）"""
        self._migration_adapter = adapter

    def _is_read_allowed(self) -> bool:
        """叙事原型读取是否被迁移阶段允许"""
        if self._migration_adapter is None:
            return True
        phase = self._migration_adapter.phase
        # DUAL_READ 及以后才允许读取
        from ..migration.migration_adapter import MigrationPhase
        return phase not in (MigrationPhase.LEGACY_ONLY, MigrationPhase.DUAL_WRITE)

    async def observe(
        self,
        text: str,
        valence: Valence = Valence.NEUTRAL,
        timestamp: float | None = None,
        source_id: str = "",
        session_id: str = "",
    ) -> ObserveResult:
        result = await self._observer.observe(text, valence, timestamp, source_id, session_id)

        # fire-and-forget 通知 CS/NW
        for mr in result.memory_results:
            if not mr.remembered or not mr.observation_id:
                continue
            try:
                asyncio.create_task(self._cognitive_stratifier.notify_observation(
                    mr.observation_id, result.concept_names, result.extraction.valence, mr.agent_id,
                ))
                asyncio.create_task(self._narrative_weaver.notify_observation(
                    mr.observation_id, mr.agent_id,
                ))
            except Exception:
                logger.debug("fire-and-forget notify failed for %s", mr.observation_id, exc_info=True)

        return result

    def recall(
        self,
        seeds: list[str],
        agent_id: str,
        min_weight: float = 0.05,
        max_results: int = 20,
    ) -> list[RecallItem]:
        personality = self._personality_registry.get_personality(agent_id)
        return self._spreading_activation.recall(seeds, agent_id, personality, min_weight, max_results)

    def recall_with_intuition(
        self,
        seeds: list[str],
        context_text: str,
        agent_id: str,
        min_weight: float = 0.05,
        max_results: int = 20,
        max_tokens: int = 800,
    ) -> dict:
        """recall + intuition 合并：概念激活 + 认知和叙事深度"""
        recall_items = self.recall(seeds, agent_id, min_weight, max_results)
        intuition = self.get_intuition(context_text, agent_id, max_tokens)
        return {
            "recall_items": recall_items,
            "intuition": intuition,
        }

    async def derive_profile(self, subject: str, observer: str, now: float | None = None) -> ProfileView:
        return await self._profile_deriver.derive_profile(subject, observer, now)

    async def reflect(self, subject: str, agent_id: str) -> ReflectResult:
        return await self._profile_deriver.reflect(subject, agent_id)

    async def granular_decay(self, elapsed_hours: float = 1.0) -> DecayResult:
        return await self._granular_decay_engine.granular_decay(elapsed_hours)

    def register_agent(self, agent_id: str, personality: MemoryPersonalityV2, voices: list[InnerVoice]) -> None:
        self._personality_registry.register_agent(agent_id, personality, voices)

    # ── 叙事原型委托方法 ──────────────────────────────

    async def weave_narrative(self, agent_id: str = "") -> dict:
        """触发叙事编织"""
        return await self._narrative_weaver.weave(agent_id)

    def get_intuition(self, context_text: str, agent_id: str, max_tokens: int = 800) -> dict:
        """直觉触发——DUAL_READ 及以后阶段才返回结果"""
        if not self._is_read_allowed():
            return {"triggered_entries": [], "triggered_episodes": [], "triggered_sagas": [], "cached_entities": [], "token_estimate": 0, "trigger_stats": {}}
        return self._intuition_engine.intuition_trigger(context_text, agent_id, max_tokens)

    def advance_lifecycle(self, agent_id: str = "") -> LifecycleResult:
        """推进叙事元素生命周期"""
        return self._lifecycle_manager.advance_lifecycle(agent_id)

    def process_cognitive_decay(self, agent_id: str = "") -> CognitiveDecayResult:
        """处理认知衰减"""
        return self._cognitive_stratifier.process_cognitive_decay(agent_id)

    def get_cognitive_entries(self, agent_id: str, concept: str = "") -> list:
        """查询认知条目——DUAL_READ 及以后阶段才返回结果"""
        if not self._is_read_allowed():
            return []
        return self._cognitive_stratifier.get_cognitive_entries(agent_id, concept)

    def add_cognitive_evidence(self, entry_id: int, observation_id: str, is_confirm: bool) -> None:
        """添加认知证据"""
        self._cognitive_stratifier.add_cognitive_evidence(entry_id, observation_id, is_confirm)

    # ── 心跳协调 ──────────────────────────────────────

    async def heartbeat_maintenance(self, agent_id: str = "", elapsed_hours: float = 1.0) -> dict:
        """心跳维护：granular_decay → advance_lifecycle → process_cognitive_decay"""
        import time as _time
        start = _time.monotonic()

        decay_result = await self.granular_decay(elapsed_hours)
        lifecycle_result = self.advance_lifecycle(agent_id)
        cognitive_decay_result = self.process_cognitive_decay(agent_id)

        elapsed = (_time.monotonic() - start) * 1000
        logger.debug(
            "heartbeat: decay=%d, lifecycle_fragments=%d, cognitive_processed=%d, %.1fms",
            decay_result.traces_processed,
            lifecycle_result.fragments_advanced,
            cognitive_decay_result.entries_processed,
            elapsed,
        )
        return {
            "decay": decay_result,
            "lifecycle": lifecycle_result,
            "cognitive_decay": cognitive_decay_result,
            "elapsed_ms": elapsed,
        }

    # ── 统计 ──────────────────────────────────────────

    def memory_stats(self) -> dict:
        return {
            "trace_count": self._trace_store.trace_count(),
            "concept_count": self._concept_index.concept_count(),
            "agent_stats": self._trace_store.trace_count_by_agent(),
            "registered_agents": self._personality_registry.registered_agents(),
            "fragment_count": len(self._episode_store.query_fragments_status()),
            "episode_count": len(self._episode_store.query_episodes_by_agent("")),
            "saga_count": len(self._episode_store.query_sagas_by_agent("")),
            "cognitive_entry_count": len(self._cognitive_stratifier.get_cognitive_entries("")),
        }
