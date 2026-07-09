from __future__ import annotations

from typing import Any

from src.common.logger import get_logger
from src.core.types import MemoryHit, MemorySearchResult

from ..connectionist.models import ProfileView, RecallItem

logger = get_logger("ConnectionistTranslator")

_DEPTH_LABELS: dict[str, str] = {
    "空白": "无了解",
    "初识": "初步了解",
    "相识": "较为熟悉",
    "熟悉": "非常熟悉",
    "深知": "深刻理解",
}


class ConnectionistTranslator:
    """连接主义→分类学 格式翻译层（纯函数，无副作用）"""

    @staticmethod
    def recall_to_search_result(items: list[RecallItem], query: str) -> MemorySearchResult:
        if not items:
            return MemorySearchResult(summary=query)
        hits = []
        for item in items:
            hits.append(MemoryHit(
                content=item.concept,
                score=item.activation,
                hit_type="connectionist_trace",
                metadata={
                    "valence": item.valence.value,
                    "detail_level": item.detail_level,
                    "relative_time": item.relative_time,
                },
            ))
        return MemorySearchResult(summary=query, hits=hits)

    @staticmethod
    def profile_view_to_dict(profile: ProfileView) -> dict[str, Any]:
        if not profile.associations and not profile.contradictions:
            return {
                "success": True,
                "summary": _DEPTH_LABELS.get(profile.depth, profile.depth),
                "traits": [],
                "evidence": [],
            }

        evidence = []
        for assoc in profile.associations:
            evidence.append({
                "concept": assoc.concept,
                "strength": assoc.strength,
                "valence": assoc.valence.value,
                "voice": assoc.voice,
            })

        traits = []
        for c in profile.contradictions:
            traits.append({
                "type": "contradiction",
                "concept": c.concept,
                "voice_a": c.voice_a,
                "valence_a": c.valence_a.value,
                "voice_b": c.voice_b,
                "valence_b": c.valence_b.value,
            })

        return {
            "success": True,
            "summary": _DEPTH_LABELS.get(profile.depth, profile.depth),
            "traits": traits,
            "evidence": evidence,
        }

    @staticmethod
    def profile_view_to_injection_text(profile: ProfileView) -> str:
        parts = []
        depth_desc = _DEPTH_LABELS.get(profile.depth, profile.depth)
        if depth_desc:
            parts.append(f"熟悉度: {depth_desc}")

        sorted_assoc = sorted(profile.associations, key=lambda a: a.strength, reverse=True)
        if sorted_assoc:
            assoc_strs = []
            for a in sorted_assoc[:8]:
                assoc_strs.append(f"{a.concept}({a.strength:.1f})")
            parts.append("关联概念: " + ", ".join(assoc_strs))

        if profile.contradictions:
            contra_strs = []
            for c in profile.contradictions[:3]:
                contra_strs.append(f"{c.concept}: {c.voice_a}({c.valence_a.value}) vs {c.voice_b}({c.valence_b.value})")
            parts.append("矛盾: " + "; ".join(contra_strs))

        return "\n".join(parts)

    @staticmethod
    def query_to_seeds(query: str, concept_index=None) -> list[str]:
        if not query or not query.strip():
            return []
        query = query.strip()
        if len(query) <= 4:
            seeds = [query]
        else:
            try:
                import jieba
                words = [w.strip() for w in jieba.cut(query) if w.strip() and len(w.strip()) >= 2]
                seeds = words if words else [query]
            except Exception:
                seeds = [query]

        if concept_index is not None:
            try:
                expanded = concept_index.expand_seeds(seeds)
                return expanded
            except Exception:
                pass
        return seeds