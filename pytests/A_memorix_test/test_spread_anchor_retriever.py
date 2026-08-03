"""MF-P3-001/002/005 验收：SpreadAnchorRetriever 扩散-锚定检索。

对应 tasks.md 6.2：事实锚定有命中→anchored；无命中→unanchored；扩散深度截断；
评分归一化异常→degraded；结果同时含事实与联想上下文。
"""

import pytest

from src.A_memorix.core.concept_graph import (
    AnchorStatus,
    ConceptGraph,
    ConceptGraphStore,
    SourceType,
)
from src.A_memorix.core.concept_graph.score_normalizer import ScoreNormalizer
from src.A_memorix.core.concept_graph.spread_anchor_retriever import SpreadAnchorRetriever


@pytest.fixture
def graph(tmp_path) -> ConceptGraph:
    store = ConceptGraphStore(tmp_path)
    store.init_schema()
    graph = ConceptGraph(store)
    # 图：生日 → 琪亚娜 → 银狼（两条 trace 链）
    birthday = graph.add_concept(name="生日")
    kiana = graph.add_concept(name="琪亚娜")
    wolf = graph.add_concept(name="银狼")
    graph.add_trace_edge(source_id=birthday.id, target_id=kiana.id, perspective="回忆", weight=0.8)
    graph.add_trace_edge(source_id=kiana.id, target_id=wolf.id, perspective="回忆", weight=0.6)
    yield graph
    store.close()


def _retriever(graph: ConceptGraph, vector_results: dict[str, float] | None = None):
    def _vector(query: str, top_n: int) -> list[tuple[str, float]]:
        if not vector_results:
            return []
        return [(cid, s) for cid, s in vector_results.items()][:top_n]

    return SpreadAnchorRetriever(
        graph,
        score_normalizer=ScoreNormalizer(),
        vector_retriever=_vector if vector_results else None,
    )


def test_anchored_retrieval_with_spread(graph: ConceptGraph) -> None:
    """事实锚定命中 → anchored；扩散到二跳（银狼）。"""
    retriever = _retriever(graph)
    result = retriever.retrieve("生日", max_depth=3, min_weight=0.05)
    assert result.anchor_status == AnchorStatus.ANCHORED
    assert result.items
    names = {item.context for item in result.items}
    assert "生日" in names
    assert "琪亚娜" in names  # 一跳
    assert "银狼" in names  # 二跳（深度衰减仍 > 0）


def test_depth_truncation(graph: ConceptGraph) -> None:
    """max_depth=1：只到一跳，银狼不可达。"""
    retriever = _retriever(graph)
    result = retriever.retrieve("生日", max_depth=1, min_weight=0.05)
    names = {item.context for item in result.items}
    assert "琪亚娜" in names
    assert "银狼" not in names


def test_unanchored_falls_back_to_spread(graph: ConceptGraph) -> None:
    """无事实锚定 → unanchored + 纯联想扩散（无向量补充时）。"""
    retriever = _retriever(graph)
    result = retriever.retrieve("完全不存在的概念词", max_depth=2, min_weight=0.05)
    assert result.anchor_status == AnchorStatus.UNANCHORED
    assert result.items == []  # 无锚点 → 无扩散起点


def test_vector_supplement_merges(graph: ConceptGraph) -> None:
    """向量补充：命中项以向量分参与融合。"""
    kiana_id = graph._store.get_node_by_name("琪亚娜").id
    retriever = _retriever(graph, vector_results={kiana_id: 0.9})
    result = retriever.retrieve("生日", max_depth=1, min_weight=0.05)
    assert result.anchor_status == AnchorStatus.ANCHORED
    item = next(i for i in result.items if i.concept_id == kiana_id)
    assert item.source_type in (SourceType.HYBRID, SourceType.FACT_ANCHOR)


def test_source_type_marking(graph: ConceptGraph) -> None:
    """扩散命中 → ASSOCIATION_SPREAD。"""
    retriever = _retriever(graph)
    result = retriever.retrieve("生日", max_depth=3, min_weight=0.05)
    wolf_id = graph._store.get_node_by_name("银狼").id
    wolf_item = next(i for i in result.items if i.concept_id == wolf_id)
    assert wolf_item.source_type == SourceType.ASSOCIATION_SPREAD


def test_min_weight_filters_weak_edges(graph: ConceptGraph) -> None:
    """min_weight 过滤：高于阈值才扩散。"""
    retriever = _retriever(graph)
    result = retriever.retrieve("生日", max_depth=3, min_weight=0.9)
    # 生日→琪亚娜 weight=0.8 < 0.9 → 无扩散
    names = {item.context for item in result.items}
    assert "琪亚娜" not in names
    assert "生日" in names  # 锚点本身在


def test_normalizer_failure_degrades(graph: ConceptGraph) -> None:
    """评分归一化异常 → degraded + 纯事实检索降级。"""

    class _BrokenNormalizer:
        def normalize(self, **kwargs):
            raise RuntimeError("归一化崩溃")

    retriever = SpreadAnchorRetriever(graph, score_normalizer=_BrokenNormalizer())
    result = retriever.retrieve("生日", max_depth=1, min_weight=0.05)
    assert result.anchor_status == AnchorStatus.DEGRADED
