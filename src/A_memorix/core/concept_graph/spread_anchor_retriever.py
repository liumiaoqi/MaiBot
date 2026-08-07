"""SpreadAnchorRetriever — 扩散-锚定检索器（MF-P3-001/002/005/006）。

流程（单次遍历，非 RRF 拼接）：
1. 概念解析(query) → 种子概念列表
2. 事实锚定：ConceptGraphStore 精确匹配种子概念（命中 → anchored）
3. 激活扩散：从锚点沿 TraceEdge 扩散（深度 ≤ max_depth，min_weight 过滤）
4. 向量补充：VectorStore HNSW top-N（可选注入）
5. ScoreNormalizer：扩散分 + 向量相似度 → 统一 [0,1] 评分空间
6. 合并去重 + 排序 → FusionSearchResult（带 anchor_status）

降级策略：
- 事实锚定无命中 → 纯联想扩散 + anchor_status=unanchored
- 评分归一化异常 → 纯事实检索 + anchor_status=degraded
"""

from collections import deque
from typing import Callable, Optional

from src.common.logger import get_logger

from .concept_graph import ConceptGraph
from .models import (
    AnchorStatus,
    ConceptNode,
    FusionSearchItem,
    FusionSearchResult,
    SourceType,
)
from .score_normalizer import ScoreNormalizer

logger = get_logger("A_Memorix.SpreadAnchorRetriever")

_DEFAULT_MAX_DEPTH = 3
_DEFAULT_MIN_WEIGHT = 0.05
_DEFAULT_LIMIT = 10


class SpreadAnchorRetriever:
    """扩散-锚定融合检索器。"""

    def __init__(
        self,
        concept_graph: ConceptGraph,
        score_normalizer: Optional[ScoreNormalizer] = None,
        vector_retriever: Optional[Callable[[str, int], list[tuple[str, float]]]] = None,
        score_alpha: float = 0.5,
    ) -> None:
        """初始化。

        Args:
            concept_graph: 概念图
            score_normalizer: 评分归一化器（默认新建）
            vector_retriever: 向量检索回调 (query, top_n) → [(concept_id, similarity)]；
                未注入时跳过向量补充
            score_alpha: 扩散分权重（CX-P1：接线 memory_fusion.score_alpha）
        """
        self._graph = concept_graph
        self._normalizer = score_normalizer or ScoreNormalizer()
        self._vector_retriever = vector_retriever
        self._score_alpha = max(0.0, min(1.0, score_alpha))
        # CX-P1-E1：扩散路径上的入边权重（BFS 入队时记录，取最大）
        self._incoming_weights: dict[str, float] = {}

    def retrieve(
        self,
        query: str,
        *,
        agent_id: str = "",
        limit: int = _DEFAULT_LIMIT,
        max_depth: int = _DEFAULT_MAX_DEPTH,
        min_weight: float = _DEFAULT_MIN_WEIGHT,
    ) -> FusionSearchResult:
        """扩散-锚定检索（单次遍历，非 RRF）。"""
        seeds = self._resolve_seed_concepts(query)

        # 事实锚定：精确匹配种子概念（概念名匹配）
        anchors = [
            node for node in (self._graph.get_node(node.id) for node in seeds)
            if node is not None
        ]
        anchor_status = AnchorStatus.ANCHORED if anchors else AnchorStatus.UNANCHORED
        spread_start = anchors if anchors else seeds

        # 激活扩散：从锚点沿 TraceEdge BFS
        spread_scores: dict[str, float] = {}
        anchor_ids = {node.id for node in anchors}
        try:
            self._spread(
                start_nodes=spread_start,
                agent_id=agent_id,
                max_depth=max_depth,
                min_weight=min_weight,
                scores=spread_scores,
            )
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, '联想扩散异常，降级纯事实检索: %s', exception=exc)
            logger.warning("联想扩散异常，降级纯事实检索: %s", exc)
            anchor_status = AnchorStatus.DEGRADED
            spread_scores = {}

        # 向量补充（可选）
        vector_scores: dict[str, float] = {}
        if self._vector_retriever is not None:
            try:
                for cid, score in self._vector_retriever(query, max(5, limit * 2)):
                    vector_scores[cid] = max(0.0, float(score))
            except Exception as exc:
                from src.core.error_escalation.types import ErrorLevel
                from src.core.error_escalation_port_registry import get_error_escalation_port
                port = get_error_escalation_port()
                if port is not None:
                    port.report(ErrorLevel.WARNING, '向量补充失败（忽略）: %s', exception=exc)
                logger.warning("向量补充失败（忽略）: %s", exc)

        # 评分归一化合并
        try:
            fused = self._normalizer.normalize(
                spread_scores=spread_scores,
                vector_scores=vector_scores,
                alpha=self._score_alpha,
            )
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, '评分归一化异常，降级纯事实检索: %s', exception=exc)
            logger.warning("评分归一化异常，降级纯事实检索: %s", exc)
            anchor_status = AnchorStatus.DEGRADED
            fused = dict(spread_scores)

        # 锚点保底：事实命中是绝对标记，不被归一化抹平（CX-P1-E3）
        for anchor_id in anchor_ids:
            fused[anchor_id] = max(fused.get(anchor_id, 0.0), 1.0)

        items = self._build_items(
            fused=fused,
            spread_scores=spread_scores,
            anchor_ids=anchor_ids,
            vector_scores=vector_scores,
            limit=limit,
        )
        return FusionSearchResult(
            query=query,
            items=items,
            anchor_status=anchor_status,
        )

    # ── 内部 ──────────────────────────────────────────────

    def _resolve_seed_concepts(self, query: str) -> list[ConceptNode]:
        """概念解析：query 分词/整体作为种子概念（概念名子串匹配）。"""
        clean = str(query or "").strip()
        if not clean:
            return []
        seeds: list[ConceptNode] = []
        seen: set[str] = set()
        # 整句优先（概念名含 query），再尝试分词
        for token in (clean, *clean.split()):
            if token in seen or not token:
                continue
            seen.add(token)
            node = self._graph._store.get_node_by_name(token)
            if node is not None:
                seeds.append(node)
        return seeds

    def _spread(
        self,
        *,
        start_nodes: list[ConceptNode],
        agent_id: str,
        max_depth: int,
        min_weight: float,
        scores: dict[str, float],
    ) -> None:
        """BFS 扩散：每层沿 TraceEdge，深度衰减 0.85^depth × 入边权重。"""
        max_depth = max(1, int(max_depth))
        self._incoming_weights.clear()
        visited: set[str] = set()
        queue: deque[tuple[ConceptNode, int]] = deque(
            (node, 0) for node in start_nodes
        )
        while queue:
            node, depth = queue.popleft()
            if node.id in visited:
                continue
            visited.add(node.id)
            if depth == 0:
                scores[node.id] = 1.0  # 锚点本身是事实命中
            else:
                # CX-P1-E1：扩散分 = 深度衰减 × 入边权重（0.9 与 0.06 权重可区分）
                incoming = self._incoming_weights.get(node.id, 0.0)
                scores[node.id] = max(
                    scores.get(node.id, 0.0),
                    0.85 ** depth * incoming,
                )
            if depth >= max_depth:
                continue
            for edge in self._graph.get_adjacent_traces(node.id, agent_id):
                if edge.weight < min_weight:
                    continue
                # CX-P1-E2：双向扩散——入边（node 是 target）的邻居是 source
                neighbor_id = (
                    edge.target_concept_id
                    if edge.source_concept_id == node.id
                    else edge.source_concept_id
                )
                self._incoming_weights[neighbor_id] = max(
                    self._incoming_weights.get(neighbor_id, 0.0),
                    edge.weight,
                )
                target = self._graph.get_node(neighbor_id)
                if target is not None:
                    queue.append((target, depth + 1))

    def _build_items(
        self,
        *,
        fused: dict[str, float],
        spread_scores: dict[str, float],
        anchor_ids: set[str],
        vector_scores: dict[str, float],
        limit: int,
    ) -> list[FusionSearchItem]:
        """合并去重 + 排序 → items。

        标注（CX-P1-E5）：锚点 → FACT_ANCHOR；扩散命中 → ASSOCIATION_SPREAD；
        仅向量命中 → FACT_ANCHOR（向量侧 = 事实侧）。
        """
        ordered = sorted(fused.items(), key=lambda kv: -kv[1])
        items: list[FusionSearchItem] = []
        for cid, score in ordered[:limit]:
            node = self._graph.get_node(cid)
            if node is None:
                continue
            if cid in anchor_ids:
                source_type = SourceType.FACT_ANCHOR
            elif cid in spread_scores and cid in vector_scores:
                source_type = SourceType.HYBRID
            elif cid in spread_scores:
                source_type = SourceType.ASSOCIATION_SPREAD
            else:
                source_type = SourceType.FACT_ANCHOR
            items.append(FusionSearchItem(
                concept_id=cid,
                score=score,
                source_type=source_type,
                context=node.name,
            ))
        return items
