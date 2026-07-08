from __future__ import annotations

import time

from ..connectionist.concept_index import ConceptIndex
from ..connectionist.enums import Valence
from ..connectionist.models import MemoryPersonalityV2, RecallItem, Trace
from ..connectionist.trace_store import TraceStore
from ..connectionist.models import _relative_time_from_timestamp


class SpreadingActivation:
    """激活扩散回忆算法"""

    DECAY_COEFFICIENT = 0.85

    def __init__(self, trace_store: TraceStore, concept_index: ConceptIndex) -> None:
        self._trace_store = trace_store
        self._concept_index = concept_index

    def recall(
        self,
        seeds: list[str],
        agent_id: str,
        personality: MemoryPersonalityV2,
        min_weight: float = 0.05,
        max_results: int = 20,
    ) -> list[RecallItem]:
        expanded_seeds = self._concept_index.expand_seeds(seeds)
        association_depth = personality.association_depth

        activated: dict[str, float] = {}
        valence_map: dict[str, Valence] = {}
        detail_map: dict[str, float] = {}
        time_map: dict[str, float] = {}

        for seed in expanded_seeds:
            activated[seed] = 1.0

        frontier = set(expanded_seeds)

        for _ in range(association_depth):
            next_frontier: set[str] = set()
            for concept in frontier:
                current_activation = activated.get(concept, 0.0)
                if current_activation < min_weight:
                    continue

                adjacent_traces = self._trace_store.get_adjacent_concepts(concept, agent_id)
                for trace in adjacent_traces:
                    neighbor = trace.target if trace.source == concept else trace.source

                    recency_factor = 1.0
                    if trace.timestamp > 0:
                        hours_ago = (time.time() - trace.timestamp) / 3600
                        if hours_ago < 1.0:
                            recency_factor = 1.0 + 0.5 * (1.0 - hours_ago)

                    detail_factor = 0.3 + 0.7 * trace.detail_level

                    spread = current_activation * trace.weight * self.DECAY_COEFFICIENT * recency_factor * detail_factor

                    if spread >= min_weight:
                        if neighbor not in activated or spread > activated.get(neighbor, 0.0):
                            activated[neighbor] = spread
                            valence_map[neighbor] = trace.valence
                            detail_map[neighbor] = trace.detail_level
                            time_map[neighbor] = trace.timestamp
                            next_frontier.add(neighbor)

            frontier = next_frontier
            if not frontier:
                break

        now = time.time()
        results: list[RecallItem] = []
        for concept, activation in sorted(activated.items(), key=lambda x: -x[1]):
            if concept in seeds:
                continue
            if len(results) >= max_results:
                break
            ts = time_map.get(concept, 0.0)
            results.append(
                RecallItem(
                    concept=concept,
                    activation=min(1.0, activation),
                    valence=valence_map.get(concept, Valence.NEUTRAL),
                    detail_level=detail_map.get(concept, 1.0),
                    relative_time=_relative_time_from_timestamp(ts, now) if ts > 0 else "",
                )
            )

        return results