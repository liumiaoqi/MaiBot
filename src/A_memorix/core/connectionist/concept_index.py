from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.common.logger import get_logger

logger = get_logger("ConceptIndex")


class ConceptIndex:
    """概念→类型映射、同义词表、概念频率统计"""

    def __init__(self, data_dir: Path) -> None:
        self._path = data_dir / "connectionist" / "concepts.json"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._concept_types: dict[str, str] = {}
        self._synonyms: dict[str, set[str]] = {}
        self._frequencies: dict[str, int] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        with open(self._path, encoding="utf-8") as f:
            data = json.load(f)
        self._concept_types = data.get("concept_types", {})
        self._synonyms = {k: set(v) for k, v in data.get("synonyms", {}).items()}
        self._frequencies = data.get("frequencies", {})

    def _save(self) -> None:
        data = {
            "concept_types": self._concept_types,
            "synonyms": {k: sorted(v) for k, v in self._synonyms.items()},
            "frequencies": self._frequencies,
        }
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def register_concept(self, name: str, concept_type: str = "unknown") -> None:
        if name in self._concept_types:
            return
        self._concept_types[name] = concept_type
        self._frequencies[name] = self._frequencies.get(name, 0)
        self._save()

    def get_type(self, name: str) -> str:
        return self._concept_types.get(name, "unknown")

    def register_synonym(self, word: str, synonym_of: str) -> None:
        self._synonyms.setdefault(synonym_of, set()).add(word)
        self._synonyms.setdefault(word, set()).add(synonym_of)
        self._save()

    def get_synonyms(self, word: str) -> set[str]:
        return self._synonyms.get(word, set())

    def expand_seeds(self, seeds: list[str]) -> list[str]:
        expanded = set(seeds)
        for seed in seeds:
            expanded |= self.get_synonyms(seed)
        return list(expanded)

    def increment_count(self, name: str) -> None:
        self._frequencies[name] = self._frequencies.get(name, 0) + 1
        self._save()

    def get_count(self, name: str) -> int:
        return self._frequencies.get(name, 0)

    def all_concepts(self) -> dict[str, str]:
        return dict(self._concept_types)

    def concept_count(self) -> int:
        return len(self._concept_types)