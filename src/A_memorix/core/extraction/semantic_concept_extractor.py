from __future__ import annotations

import re

import jieba
import jieba.posseg as pseg

from src.common.logger import get_logger

from ..connectionist.enums import Valence
from ..connectionist.models import ExtractedConcept, ExtractionResult

logger = get_logger("SemanticConceptExtractor")

_POS_TYPE_MAP: dict[str, str] = {
    "nr": "person",
    "ns": "place",
    "nt": "organization",
    "nz": "object",
    "n": "abstract",
    "v": "activity",
    "vd": "activity",
    "vn": "activity",
    "a": "emotion",
    "ad": "emotion",
    "an": "emotion",
}

_STOP_POS: frozenset[str] = frozenset({
    "p", "c", "u", "d", "m", "q", "r", "t", "f", "b", "j", "l",
})


class SemanticConceptExtractor:
    """jieba 分词 + ConceptIndex 同义词归一化的降级概念提取器"""

    def __init__(self, concept_index) -> None:
        self._concept_index = concept_index

    async def extract(self, text: str) -> ExtractionResult:
        if not text or not text.strip():
            return ExtractionResult()

        try:
            concepts = self._extract_concepts(text)
            return ExtractionResult(
                concepts=concepts,
                valence=Valence.NEUTRAL,
            )
        except Exception as e:
            logger.error(f"jieba 概念提取失败: {e}")
            return ExtractionResult()

    def _extract_concepts(self, text: str) -> list[ExtractedConcept]:
        words = pseg.cut(text)
        seen: set[str] = set()
        concepts: list[ExtractedConcept] = []

        for word, flag in words:
            word = word.strip()
            if not word or len(word) < 2:
                continue
            if flag.lower() in _STOP_POS:
                continue
            if re.match(r"^[\d\s\W]+$", word):
                continue

            normalized = self._normalize(word)
            if normalized in seen:
                continue
            seen.add(normalized)

            concept_type = self._concept_index.get_type(normalized) if self._concept_index else "unknown"
            if concept_type == "unknown":
                concept_type = _POS_TYPE_MAP.get(flag.lower(), "abstract")

            concepts.append(ExtractedConcept(
                name=normalized,
                concept_type=concept_type,
                confidence=0.6,
            ))

        return concepts

    def _normalize(self, word: str) -> str:
        if not self._concept_index:
            return word
        synonyms = self._concept_index.get_synonyms(word)
        all_concepts = self._concept_index.all_concepts()
        for syn in synonyms:
            if syn in all_concepts:
                return syn
        return word