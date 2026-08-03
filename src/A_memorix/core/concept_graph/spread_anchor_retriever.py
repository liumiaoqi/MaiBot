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
    ) -> None:
        """初始化。

        Args:
            concept_graph: 概念图
            score_normalizer: 评分归一化器（默认新建）
            vector_retriever: 向量检索回调 (query, top_n) → [(concept_id, similarity)]；
                未注入时跳过向量补充
        """
        self._graph = concept_graph
        self._normalizer = score_normalizer or ScoreNormalizer()
        self._vector_retriever = vector_retriever

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
        try:
            self._spread(
                start_nodes=spread_start,
                agent_id=agent_id,
                max_depth=max_depth,
                min_weight=min_weight,
                scores=spread_scores,
            )
        except Exception as exc:
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
                logger.warning("向量补充失败（忽略）: %s", exc)

        # 评分归一化合并
        try:
            fused = self._normalizer.normalize(
                spread_scores=spread_scores,
                vector_scores=vector_scores,
                alpha=0.5,
            )
        except Exception as exc:
            logger.warning("评分归一化异常，降级纯事实检索: %s", exc)
            anchor_status = AnchorStatus.DEGRADED
            fused = dict(spread_scores)

        items = self._build_items(
            fused=fused,
            spread_scores=spread_scores,
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
        """BFS 扩散：每层沿 TraceEdge，深度衰减 0.85^depth × weight。"""
        max_depth = max(1, int(max_depth))
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
                scores[node.id] = max(
                    scores.get(node.id, 0.0),
                    0.85 ** depth,
                )
            if depth >= max_depth:
                continue
            for edge in self._graph.get_adjacent_traces(node.id, agent_id):
                if edge.weight < min_weight:
                    continue
                target = self._graph.get_node(edge.target_concept_id)
                if target is not None:
                    queue.append((target, depth + 1))

    def _build_items(
        self,
        *,
        fused: dict[str, float],
        spread_scores: dict[str, float],
        vector_scores: dict[str, float],
        limit: int,
    ) -> list[FusionSearchItem]:
        """合并去重 + 排序 → items。"""
        ordered = sorted(fused.items(), key=lambda kv: -kv[1])
        items: list[FusionSearchItem] = []
        for cid, score in ordered[:limit]:
            node = self._graph.get_node(cid)
            if node is None:
                continue
            in_spread = cid in spread_scores
            in_vector = cid in vector_scores
            if in_spread and in_vector:
                source_type = SourceType.HYBRID
            elif in_spread:
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
