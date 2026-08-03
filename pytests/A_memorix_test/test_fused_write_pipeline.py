"""MF-P2-001/003/004/006 验收：FusedWritePipeline 统一写入管线。

对应 tasks.md 5.2：幂等（同一 event_id 跳过）；双投影同时存在（同一 SQLite
事务串行写入）；向量写入失败不回滚概念图（embedding_pending 标记）。
"""

from unittest.mock import AsyncMock

import pytest

from src.A_memorix.core.concept_graph import (
    ConceptGraph,
    ConceptGraphStore,
    EdgeSource,
    NodeCategory,
)
from src.A_memorix.core.concept_graph.fused_write_pipeline import (
    ConceptGraphWriteError,
    FusedWritePipeline,
)
from src.A_memorix.core.concept_graph.models import ConceptNode, RelationEdge, TraceEdge


@pytest.fixture
def pipeline(tmp_path) -> FusedWritePipeline:
    store = ConceptGraphStore(tmp_path)
    store.init_schema()
    graph = ConceptGraph(store)
    yield FusedWritePipeline(graph, store, embedding_writer=None)
    store.close()


def _concept(node_id: str, name: str) -> ConceptNode:
    return ConceptNode(id=node_id, name=name, type=NodeCategory.CONCEPT, created_at=1.0, updated_at=1.0)


async def test_write_produces_dual_projection(pipeline: FusedWritePipeline) -> None:
    """一次 write 同时产出事实投影（关系边）和联想投影（Trace 边）。"""
    a = _concept("a", "生日")
    b = _concept("b", "琪亚娜")
    rel = RelationEdge(
        id="r1", source_id="a", target_id="b", relation_type="庆祝",
        schema_source=EdgeSource.TAXONOMY_PROJECTION, created_at=1.0,
    )
    trace = TraceEdge(
        id="t1", source_concept_id="a", target_concept_id="b", perspective="回忆",
        weight=0.5, valence=0.8, last_activated_at=1.0, created_at=1.0,
    )
    result = await pipeline.write(event_id="e1", concepts=[a, b], relations=[rel], traces=[trace])
    assert result.written is True
    assert result.nodes_written == 2

    facts = pipeline._graph.query_fact_view(["a"])
    traces = pipeline._graph.query_association_view(["a"])
    assert len(facts) == 1
    assert len(traces) == 1


async def test_write_idempotent_same_event_id(pipeline: FusedWritePipeline) -> None:
    """同一 event_id 二次写入跳过（幂等）。"""
    a = _concept("a", "生日")
    result1 = await pipeline.write(event_id="e1", concepts=[a])
    result2 = await pipeline.write(event_id="e1", concepts=[a])
    assert result1.written is True
    assert result2.written is False
    assert len(pipeline._graph.query_fact_view(["a"])) == 0  # 无重复数据


async def test_write_idempotent_survives_restart(pipeline: FusedWritePipeline, tmp_path) -> None:
    """幂等记录持久化：重建 Store 后同一 event_id 仍跳过。"""
    a = _concept("a", "生日")
    await pipeline.write(event_id="e1", concepts=[a])
    pipeline._store.close()

    store2 = ConceptGraphStore(tmp_path)
    store2.init_schema()
    graph2 = ConceptGraph(store2)
    pipeline2 = FusedWritePipeline(graph2, store2)
    result = await pipeline2.write(event_id="e1", concepts=[_concept("a", "生日")])
    assert result.written is False
    store2.close()


async def test_embedding_failure_marks_pending_not_rollback(pipeline: FusedWritePipeline) -> None:
    """向量写入失败 → embedding_pending=True，概念图不回滚（R06）。"""
    def _failing_embedding(nodes) -> list[str]:
        raise RuntimeError("向量服务不可用")

    pipeline._embedding_writer = _failing_embedding
    a = _concept("a", "生日")
    result = await pipeline.write(event_id="e1", concepts=[a])
    assert result.written is True  # 概念图已提交
    assert result.embedding_pending == ["a"]
    node = pipeline._graph.get_node("a")
    assert node.embedding_pending is True


async def test_embedding_partial_failure_marks_missing(pipeline: FusedWritePipeline) -> None:
    """部分向量写入成功：仅未成功的节点标记 pending。"""
    pipeline._embedding_writer = lambda nodes: ["a"]  # 只有 a 成功
    a = _concept("a", "生日")
    b = _concept("b", "琪亚娜")
    result = await pipeline.write(event_id="e1", concepts=[a, b])
    assert result.embedding_pending == ["b"]
    assert pipeline._graph.get_node("b").embedding_pending is True
    assert pipeline._graph.get_node("a").embedding_pending is False


async def test_concurrent_same_nodes_serialized(pipeline: FusedWritePipeline) -> None:
    """并发写同一节点：WriteLockManager 串行化，全部成功。"""
    import asyncio

    async def writer(i: int) -> None:
        await pipeline.write(event_id=f"e{i}", concepts=[_concept("a", "生日")])

    results = await asyncio.gather(*[writer(i) for i in range(5)])
    assert all(r is None for r in results)  # writer 无返回值，gather 不抛即成功
    node = pipeline._graph.get_node("a")
    assert node is not None
    assert node.name == "生日"


async def test_empty_event_id_rejected(pipeline: FusedWritePipeline) -> None:
    with pytest.raises(ConceptGraphWriteError, match="event_id 为空"):
        await pipeline.write(event_id="", concepts=[])


async def test_observe_experience_uses_same_pipeline(pipeline: FusedWritePipeline) -> None:
    """observe_experience 入口：概念提取 → 双投影 write()（含联想 trace）。"""
    pipeline._concept_extractor = AsyncMock(return_value=["生日", "琪亚娜"])
    request = type("Req", (), {
        "text": "今天琪亚娜的生日",
        "agent_id": "silver_wolf",
        "source_id": "obs1",
        "valence": 0.5,
    })()
    result = await pipeline.observe_experience(request)
    assert result.success is True
    assert len(result.stored_ids) == 2
    # 联想投影：两概念间有 trace（perspective=agent:silver_wolf）
    traces = pipeline._graph.query_association_view([result.stored_ids[0]])
    assert len(traces) == 1
    assert traces[0].perspective == "agent:silver_wolf"


async def test_ingest_summary_uses_same_pipeline(pipeline: FusedWritePipeline) -> None:
    """ingest_summary 入口：同一 write() 管线。"""
    pipeline._concept_extractor = AsyncMock(return_value=["契约", "终焉"])
    result = await pipeline.ingest_summary(
        external_id="ext1", chat_id="chat1", text="契约与终焉的故事", agent_id="tighnari",
    )
    assert result["success"] is True
    assert result["concepts"] == ["契约", "终焉"]
    # 幂等：同 external_id 再写跳过
    result2 = await pipeline.ingest_summary(
        external_id="ext1", chat_id="chat1", text="契约与终焉的故事", agent_id="tighnari",
    )
    assert result2["success"] is False
