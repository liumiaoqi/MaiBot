"""概念图数据模型（MF-P1-003）。

概念图 = 事实投影（relation_edges，分类学/关系事实）+ 联想投影
（trace_edges，连接主义激活痕迹）。节点以统一 id 标识，概念与实体同源。
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class NodeCategory(str, Enum):
    """节点类别 — type 是节点属性标签（R01 修正：generate 不含 type 参数）。"""

    CONCEPT = "concept"
    """连接主义概念（如"生日""契约"）"""
    ENTITY = "entity"
    """分类学实体（如"琪亚娜""银狼"）"""
    BOTH = "both"
    """概念-实体同源节点（统一 id 对齐后同一节点）"""


class EdgeSource(str, Enum):
    """关系边来源。"""

    TAXONOMY_PROJECTION = "taxonomy_projection"
    """分类学投影（从知识三元组/关系事实投影）"""
    CONNECTIONIST_PROJECTION = "connectionist_projection"
    """连接主义投影（从概念关联投影）"""
    MANUAL = "manual"
    """人工标注"""


class AnchorStatus(str, Enum):
    """检索锚定状态（融合检索降级策略标记）。"""

    ANCHORED = "anchored"
    """事实锚定有命中"""
    UNANCHORED = "unanchored"
    """事实锚定无命中 → 纯联想扩散"""
    DEGRADED = "degraded"
    """评分归一化异常 → 纯事实检索"""


class SourceType(str, Enum):
    """检索结果来源类型。"""

    FACT_ANCHOR = "fact_anchor"
    """事实锚定"""
    ASSOCIATION_SPREAD = "association_spread"
    """联想扩散"""
    HYBRID = "hybrid"
    """混合（事实 + 联想）"""


@dataclass(slots=True)
class ConceptNode:
    """概念/实体节点。"""

    id: str
    name: str
    type: NodeCategory = NodeCategory.CONCEPT
    embedding: Optional[bytes] = None
    embedding_pending: bool = False
    created_at: float = 0.0
    updated_at: float = 0.0


@dataclass(slots=True)
class RelationEdge:
    """事实投影关系边（分类学关系）。"""

    id: str
    source_id: str
    target_id: str
    relation_type: str
    weight: float = 1.0
    schema_source: EdgeSource = EdgeSource.TAXONOMY_PROJECTION
    created_at: float = 0.0


@dataclass(slots=True)
class TraceEdge:
    """联想投影 Trace 边（连接主义激活痕迹）。

    perspective 区分同一对概念间的多条联想通道（如"回忆""直觉"）。
    """

    id: str
    source_concept_id: str
    target_concept_id: str
    weight: float = 0.5
    valence: float = 0.0
    perspective: str = ""
    last_activated_at: float = 0.0
    decay_factor: float = 1.0
    created_at: float = 0.0


@dataclass(slots=True)
class DecayResult:
    """衰减结果统计。"""

    relation_affected: int = 0
    trace_affected: int = 0


@dataclass(slots=True)
class FusionSearchItem:
    """单条融合检索命中。"""

    concept_id: str
    score: float
    source_type: SourceType = SourceType.HYBRID
    context: str = ""


@dataclass(slots=True)
class EvidenceItem:
    """统一画像证据（事实视图）。"""

    type: str = "relation"
    content: str = ""
    confidence: float = 1.0
    source_id: str = ""


@dataclass(slots=True)
class AssociationItem:
    """统一画像联想关联（联想视图）。"""

    concept_id: str = ""
    weight: float = 0.0
    valence: float = 0.0
    perspective: str = ""


@dataclass(slots=True)
class UnifiedProfile:
    """统一画像三元组（MF-P4-001）。"""

    person_id: str = ""
    evidence: list[EvidenceItem] = field(default_factory=list)
    associations: list[AssociationItem] = field(default_factory=list)
    valence: Optional[float] = None
    derived_at: float = 0.0


@dataclass(slots=True)
class FusionSearchResult:
    """融合检索结果（扩散-锚定，非 RRF 拼接）。"""

    query: str
    items: list[FusionSearchItem] = field(default_factory=list)
    anchor_status: AnchorStatus = AnchorStatus.UNANCHORED
