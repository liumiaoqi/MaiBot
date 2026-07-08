from __future__ import annotations

from ..connectionist.enums import Valence
from ..connectionist.models import MemoryPersonalityV2


class SalienceEvaluator:
    """四维度显著性评估器"""

    def evaluate(
        self,
        concepts: list[str],
        agent_id: str,
        valence: Valence,
        personality: MemoryPersonalityV2,
        existing_concepts: frozenset[str] | None = None,
        new_concepts: frozenset[str] | None = None,
    ) -> tuple[float, str]:
        existing = existing_concepts or frozenset()
        new_set = new_concepts or frozenset()

        emotional = 0.0
        if valence != Valence.NEUTRAL:
            affinity = personality.positive_affinity if valence == Valence.POSITIVE else personality.negative_affinity
            emotional = 0.4 * affinity * personality.emotional_sensitivity

        attention_match = len(personality.attention_tags & set(concepts))
        attention_score = 0.5 * attention_match

        overlap = len(existing & set(concepts))
        relatedness = 0.2 * overlap

        novelty_count = len(new_set - existing)
        novelty = 0.15 * novelty_count if novelty_count >= 2 else 0.0

        total = min(1.0, emotional + attention_score + relatedness + novelty)

        threshold = 0.25 / max(0.5, personality.curiosity)

        reason_parts = []
        if emotional > 0:
            reason_parts.append(f"情感={emotional:.2f}")
        if attention_score > 0:
            reason_parts.append(f"关注={attention_score:.2f}")
        if relatedness > 0:
            reason_parts.append(f"关联={relatedness:.2f}")
        if novelty > 0:
            reason_parts.append(f"新颖={novelty:.2f}")
        reason = f"总分={total:.2f}(阈值={threshold:.2f}) [{', '.join(reason_parts)}]"

        return total, reason