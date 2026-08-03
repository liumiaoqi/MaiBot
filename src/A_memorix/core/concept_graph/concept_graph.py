"""ConceptGraph — 概念图核心类（MF-P1-003）。

持有 ConceptGraphStore + UnifiedIdGenerator，提供写入与双视图查询：
- 事实视图（query_fact_view）：关系边（分类学投影）
- 联想视图（query_association_view）：Trace 边（连接主义投影）
"""

import time
from typing import Optional, Sequence

from .concept_graph_store import ConceptGraphStore
from .models import (
    ConceptNode,
    DecayResult,
    EdgeSource,
    NodeCategory,
    RelationEdge,
    TraceEdge,
)
from .unified_id_generator import UnifiedIdGenerator


class ConceptGraph:
    """概念图：节点 + 双投影边。"""

    def __init__(
        self,
        store: ConceptGraphStore,
        id_generator: Optional[UnifiedIdGenerator] = None,
    ) -> None:
        self._store = store
        self._id_generator = id_generator or UnifiedIdGenerator()

    # ── 节点 ──────────────────────────────────────────────

    def add_node(
        self,
        *,
        id: str,
        name: str,
        type: NodeCategory = NodeCategory.CONCEPT,
        embedding: Optional[bytes] = None,
    ) -> ConceptNode:
        """写入节点（UPSERT 幂等）。"""
        now = time.time()
        node = ConceptNode(
            id=id,
            name=name,
            type=type,
            embedding=embedding,
            created_at=now,
            updated_at=now,
        )
        existing = self._store.get_node_by_id(id)
        if existing is not None:
            node.created_at = existing.created_at
            # 同名节点类型合并：概念+实体 → BOTH（type 是属性标签，不互相覆盖）
            node.type = _merge_categories(existing.type, node.type)
        self._store.upsert_node(node)
        return node

    def get_node(self, node_id: str) -> Optional[ConceptNode]:
        return self._store.get_node_by_id(node_id)

    def add_entity(self, *, name: str, embedding: Optional[bytes] = None) -> ConceptNode:
        """按名称写入实体节点（统一 id 从名称生成——MF-P1-001/002）。"""
        node_id = self._id_generator.generate(name)
        return self.add_node(id=node_id, name=name, type=NodeCategory.ENTITY, embedding=embedding)

    def add_concept(self, *, name: str, embedding: Optional[bytes] = None) -> ConceptNode:
        """按名称写入概念节点（统一 id 从名称生成）。"""
        node_id = self._id_generator.generate(name)
        return self.add_node(id=node_id, name=name, type=NodeCategory.CONCEPT, embedding=embedding)

    # ── 事实投影（关系边） ────────────────────────────────

    def add_relation_edge(
        self,
        *,
        source_id: str,
        target_id: str,
        relation_type: str,
        weight: float = 1.0,
        schema_source: EdgeSource = EdgeSource.TAXONOMY_PROJECTION,
        edge_id: str = "",
    ) -> RelationEdge:
        """写入关系边（UPSERT：同 source/target/relation_type 覆盖）。"""
        now = time.time()
        edge = RelationEdge(
            id=edge_id or f"rel:{now:.6f}:{source_id}:{target_id}:{relation_type}",
            source_id=source_id,
            target_id=target_id,
            relation_type=relation_type,
            weight=weight,
            schema_source=schema_source,
            created_at=now,
        )
        self._store.upsert_relation_edge(edge)
        return edge

    def query_fact_view(self, node_ids: Sequence[str]) -> list[RelationEdge]:
        """事实视图：指定节点相关的全部关系边。"""
        edges: list[RelationEdge] = []
        seen: set[str] = set()
        for node_id in node_ids:
            for edge in self._store.get_relation_edges(node_id):
                if edge.id not in seen:
                    seen.add(edge.id)
                    edges.append(edge)
        return edges

    # ── 联想投影（Trace 边） ──────────────────────────────

    def add_trace_edge(
        self,
        *,
        source_id: str,
        target_id: str,
        weight: float = 0.5,
        valence: float = 0.0,
        perspective: str = "",
        edge_id: str = "",
    ) -> TraceEdge:
        """写入 Trace 边（UPSERT：同 source/target/perspective 覆盖）。"""
        now = time.time()
        edge = TraceEdge(
            id=edge_id or f"trace:{now:.6f}:{source_id}:{target_id}:{perspective}",
            source_concept_id=source_id,
            target_concept_id=target_id,
            weight=weight,
            valence=valence,
            perspective=perspective,
            last_activated_at=now,
            created_at=now,
        )
        self._store.upsert_trace_edge(edge)
        return edge

    def query_association_view(self, node_ids: Sequence[str]) -> list[TraceEdge]:
        """联想视图：指定节点相关的全部 Trace 边。"""
        edges: list[TraceEdge] = []
        seen: set[str] = set()
        for node_id in node_ids:
            for edge in self._store.get_trace_edges(node_id):
                if edge.id not in seen:
                    seen.add(edge.id)
                    edges.append(edge)
        return edges

    def get_adjacent_traces(self, concept_id: str, agent_id: str = "") -> list[TraceEdge]:
        """相邻 Trace（激活扩散用，R07 内存索引优先）。"""
        return self._store.get_adjacent_traces(concept_id, agent_id)

    # ── 衰减 ──────────────────────────────────────────────

    def decay_all(self, *, relation_factor: float, trace_factor: float) -> DecayResult:
        """统一衰减（委托 Store，关系边与 Trace 同步衰减）。"""
        return self._store.decay_all(
            relation_factor=relation_factor,
            trace_factor=trace_factor,
        )


def _merge_categories(a: NodeCategory, b: NodeCategory) -> NodeCategory:
    """合并节点类别标签：概念+实体 → BOTH。"""
    if a == b:
        return a
    return NodeCategory.BOTH
