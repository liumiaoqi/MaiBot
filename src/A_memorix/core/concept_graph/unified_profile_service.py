"""UnifiedProfileService — 统一画像服务（MF-P4-001/004/005）。

evidence 来自事实视图（关系边），associations 来自联想视图（Trace 边），
valence 基于 associations 情感极性加权平均（LLM 增强可选）。

降级策略：
- evidence 缺失 → evidence=[] + associations 有值
- associations 缺失 → associations=[] + evidence 有值
- LLM 失败 → valence=None
"""

import time
from typing import Any, Awaitable, Callable, Optional

from src.common.logger import get_logger

from .concept_graph import ConceptGraph
from .models import AssociationItem, EvidenceItem, UnifiedProfile
from .unified_id_generator import UnifiedIdGenerator

logger = get_logger("A_Memorix.UnifiedProfileService")


class UnifiedProfileService:
    """统一画像服务（替代 PersonProfileService + ProfileDeriver 独立画像）。"""

    def __init__(
        self,
        concept_graph: ConceptGraph,
        llm_valence_enhancer: Optional[Callable[[list[AssociationItem]], Awaitable[Optional[float]]]] = None,
    ) -> None:
        """初始化。

        Args:
            concept_graph: 概念图
            llm_valence_enhancer: LLM 增强 valence 回调（可选）；
                输入 associations，返回情感极性分数或 None
        """
        self._graph = concept_graph
        self._llm_valence_enhancer = llm_valence_enhancer
        self._id_generator = UnifiedIdGenerator()

    async def get_person_profile(self, person_id: str, *, limit: int = 4) -> UnifiedProfile:
        """统一画像查询。

        Args:
            person_id: 人物 id（概念名语义）
            limit: evidence 条数上限

        Returns:
            UnifiedProfile（evidence + associations + valence 三元组）
        """
        person_node = self._graph._store.get_node_by_name(person_id)
        if person_node is None:
            return UnifiedProfile(person_id=person_id, derived_at=time.time())

        evidence = self._build_evidence(person_node.id, limit=limit)
        associations = self._build_associations(person_node.id, limit=limit)

        valence: Optional[float] = None
        if associations:
            valence = self._derive_valence(associations)
            if self._llm_valence_enhancer is not None:
                try:
                    llm_valence = await self._llm_valence_enhancer(associations)
                    if llm_valence is not None:
                        valence = llm_valence
                except Exception as exc:
                    logger.warning("LLM valence 增强失败，使用加权平均: %s", exc)

        return UnifiedProfile(
            person_id=person_id,
            evidence=evidence,
            associations=associations,
            valence=valence,
            derived_at=time.time(),
        )

    async def derive_profile(self, subject: str, *, observer: str = "") -> Any:
        """画像实时推导——兼容 MemoryServicePort.derive_profile 签名。"""
        from dataclasses import asdict

        profile = await self.get_person_profile(subject)
        return {
            "subject": subject,
            "observer": observer,
            "evidence": [asdict(e) for e in profile.evidence],
            "associations": [asdict(a) for a in profile.associations],
            "valence": profile.valence,
        }

    # ── 内部 ──────────────────────────────────────────────

    def _build_evidence(self, person_node_id: str, *, limit: int) -> list[EvidenceItem]:
        """事实视图 → evidence（关系边内容）。"""
        edges = self._graph.query_fact_view([person_node_id])
        items: list[EvidenceItem] = []
        seen: set[str] = set()
        for edge in edges:
            counterpart = edge.target_id if edge.source_id == person_node_id else edge.source_id
            node = self._graph.get_node(counterpart)
            name = node.name if node else counterpart
            content = f"{edge.relation_type}: {name}"
            if content in seen:
                continue
            seen.add(content)
            items.append(EvidenceItem(
                type=edge.relation_type,
                content=content,
                confidence=min(1.0, max(0.0, edge.weight)),
                source_id=edge.id,
            ))
            if len(items) >= limit:
                break
        return items

    def _build_associations(self, person_node_id: str, *, limit: int) -> list[AssociationItem]:
        """联想视图 → associations（Trace 边）。"""
        traces = self._graph.query_association_view([person_node_id])
        items: list[AssociationItem] = []
        for trace in traces:
            items.append(AssociationItem(
                concept_id=trace.target_concept_id,
                weight=trace.weight,
                valence=trace.valence,
                perspective=trace.perspective,
            ))
            if len(items) >= limit:
                break
        return items

    @staticmethod
    def _derive_valence(associations: list[AssociationItem]) -> Optional[float]:
        """情感极性加权平均（weight 为权）。"""
        total_weight = sum(max(0.0, a.weight) for a in associations)
        if total_weight <= 0:
            return None
        return sum(a.valence * max(0.0, a.weight) for a in associations) / total_weight
