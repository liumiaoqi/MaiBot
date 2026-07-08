from __future__ import annotations

from ..connectionist.enums import Valence
from ..connectionist.models import InnerVoice


class InnerVoiceProcessor:
    """内心声音处理器"""

    def transform_valence(self, valence: Valence, style: str | None = None, voice: InnerVoice | None = None) -> Valence:
        if voice is not None:
            return voice.transform_valence(valence)
        return valence

    def filter_concepts(
        self, concepts: list[str], voice: InnerVoice, existing: frozenset[str] | None = None
    ) -> list[str]:
        return voice.filter_concepts(concepts, existing)

    def process_experience(
        self,
        valence: Valence,
        concepts: list[str],
        voice: InnerVoice,
        existing: frozenset[str] | None = None,
    ) -> tuple[Valence, list[str]]:
        transformed = self.transform_valence(valence, voice=voice)
        filtered = self.filter_concepts(concepts, voice, existing)
        return transformed, filtered