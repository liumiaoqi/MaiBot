"""DFX 4.1 验收：融合检索性能 smoke（tasks.md 10.3）。

扩散检索（种子 ≤5、深度 ≤3）单次耗时 < 200ms 量级；
向量检索不在本 smoke 范围（vector_retriever 未接线）。
"""

import time

import pytest

from src.A_memorix.core.concept_graph import ConceptGraph, ConceptGraphStore
from src.A_memorix.core.concept_graph.spread_anchor_retriever import SpreadAnchorRetriever


def _build_graph_with_traces(tmp_path, n_concepts: int = 50) -> ConceptGraph:
    store = ConceptGraphStore(tmp_path)
    store.init_schema()
    graph = ConceptGraph(store)
    nodes = [graph.add_concept(name=f"概念{i}") for i in range(n_concepts)]
    for i in range(1, len(nodes)):
        graph.add_trace_edge(
            source_id=nodes[i - 1].id, target_id=nodes[i].id,
            perspective="链", weight=0.8,
        )
    return graph


def test_spread_retrieval_latency_smoke(tmp_path) -> None:
    """50 节点链图：单次扩散检索 < 200ms。"""
    graph = _build_graph_with_traces(tmp_path)
    retriever = SpreadAnchorRetriever(graph)

    started = time.monotonic()
    for _ in range(10):
        result = retriever.retrieve("概念0", max_depth=3, min_weight=0.05)
        assert result.items
    elapsed_ms = (time.monotonic() - started) * 1000 / 10
    assert elapsed_ms < 200, f"单次扩散检索耗时 {elapsed_ms:.1f}ms 超过 200ms"


def test_spread_retrieval_limited_edges(tmp_path) -> None:
    """大图（200 节点）检索仍快速（内存邻接索引）。"""
    graph = _build_graph_with_traces(tmp_path, n_concepts=200)
    retriever = SpreadAnchorRetriever(graph)
    started = time.monotonic()
    result = retriever.retrieve("概念100", max_depth=3, min_weight=0.05)
    elapsed_ms = (time.monotonic() - started) * 1000
    assert elapsed_ms < 200, f"大图扩散检索耗时 {elapsed_ms:.1f}ms"
    assert result.items
