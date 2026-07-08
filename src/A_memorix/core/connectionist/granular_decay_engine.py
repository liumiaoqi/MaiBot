from __future__ import annotations

import time

from src.common.logger import get_logger

from ..connectionist.enums import Valence
from ..connectionist.models import DecayResult, MemoryPersonalityV2, Trace
from ..connectionist.trace_store import TraceStore
from ..personality.personality_registry import PersonalityRegistry

logger = get_logger("GranularDecayEngine")

SKELETON = 0.1
BATCH_SIZE = 50000


class GranularDecayEngine:
    """粒度退化引擎"""

    def __init__(self, trace_store: TraceStore, personality_registry: PersonalityRegistry) -> None:
        self._trace_store = trace_store
        self._personality_registry = personality_registry

    async def granular_decay(self, elapsed_hours: float = 1.0) -> DecayResult:
        start = time.monotonic()
        processed = 0
        consolidated = 0

        traces_to_update: list[Trace] = []
        for trace in self._trace_store.all_traces():
            personality = self._personality_registry.get_personality(trace.agent_id)

            emotional_slowdown = 1.0 / (1.0 + 0.5 * abs(trace.valence.value_int) * personality.emotional_sensitivity)

            detail_decay = 0.01 * personality.decay_rate * elapsed_hours * emotional_slowdown
            new_detail = max(SKELETON, trace.detail_level - detail_decay)

            decay_factor = 0.995 ** (elapsed_hours * personality.decay_rate)
            emotional_floor = trace.emotional_floor_for(personality.emotional_sensitivity)
            new_weight = max(emotional_floor, trace.weight * decay_factor)

            if new_detail != trace.detail_level or new_weight != trace.weight:
                trace.detail_level = new_detail
                trace.weight = new_weight
                traces_to_update.append(trace)

            processed += 1

        if traces_to_update:
            await self._trace_store.batch_upsert(traces_to_update)

        elapsed_ms = (time.monotonic() - start) * 1000
        return DecayResult(
            traces_processed=processed,
            traces_consolidated=consolidated,
            elapsed_ms=elapsed_ms,
        )

    async def consolidate(self) -> int:
        return 0