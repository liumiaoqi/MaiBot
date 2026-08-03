"""MF-P1-003 验收：概念图 schema + 双视图 + 衰减 + 内存邻接索引。

对应 tasks.md 4.3-4.5：ConceptGraphStore 表创建/UPSERT 幂等/查询/衰减/R07
内存邻接索引；ConceptGraph 双视图（事实/联想）；FusedDecayEngine 统一衰减。
"""

from pathlib import Path

import pytest

from src.A_memorix.core.concept_graph import (
    ConceptGraph,
    ConceptGraphStore,
    EdgeSource,
    FusedDecayEngine,
    NodeCategory,
)
from src.A_memorix.core.concept_graph.concept_graph_store import _DB_FILE
from src.A_memorix.core.concept_graph.models import ConceptNode, RelationEdge, TraceEdge


@pytest.fixture
def store(tmp_path: Path) -> ConceptGraphStore:
    s = ConceptGraphStore(tmp_path)
    s.init_schema()
    yield s
    s.close()


@pytest.fixture
def graph(store: ConceptGraphStore) -> ConceptGraph:
    return ConceptGraph(store)


def _add_node(store: ConceptGraphStore, node_id: str) -> None:
    """写入节点以满足外键引用。"""
    store.upsert_node(ConceptNode(id=node_id, name=node_id, created_at=1.0, updated_at=1.0))


def test_schema_creates_tables(store: ConceptGraphStore) -> None:
    tables = {
        row[0]
        for row in store._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert {"concept_nodes", "relation_edges", "trace_edges"} <= tables


def test_upsert_node_idempotent(store: ConceptGraphStore) -> None:
    node = ConceptNode(id="n1", name="生日", type=NodeCategory.CONCEPT, created_at=1.0, updated_at=1.0)
    store.upsert_node(node)
    node.updated_at = 2.0
    store.upsert_node(node)
    assert store.get_node_by_id("n1").updated_at == 2.0


def test_upsert_relation_edge_idempotent(store: ConceptGraphStore) -> None:
    _add_node(store, "a")
    _add_node(store, "b")
    edge = RelationEdge(
        id="r1", source_id="a", target_id="b", relation_type="包含",
        weight=1.0, schema_source=EdgeSource.TAXONOMY_PROJECTION, created_at=1.0,
    )
    store.upsert_relation_edge(edge)
    edge.weight = 0.5
    store.upsert_relation_edge(edge)
    edges = store.get_relation_edges("a")
    assert len(edges) == 1
    assert edges[0].weight == 0.5


def test_upsert_trace_edge_idempotent(store: ConceptGraphStore) -> None:
    _add_node(store, "a")
    _add_node(store, "b")
    edge = TraceEdge(
        id="t1", source_concept_id="a", target_concept_id="b", perspective="回忆",
        weight=0.5, valence=0.2, last_activated_at=1.0, decay_factor=1.0, created_at=1.0,
    )
    store.upsert_trace_edge(edge)
    edge.weight = 0.9
    store.upsert_trace_edge(edge)
    traces = store.get_trace_edges("a")
    assert len(traces) == 1
    assert traces[0].weight == 0.9


def test_adjacency_index_consistency(store: ConceptGraphStore) -> None:
    """R07：内存邻接索引与 SQLite 一致（UPSERT 覆盖不重复）。"""
    _add_node(store, "a")
    _add_node(store, "b")
    _add_node(store, "c")
    edge1 = TraceEdge(
        id="t1", source_concept_id="a", target_concept_id="b", perspective="p1",
        weight=0.5, valence=0.0, last_activated_at=1.0, decay_factor=1.0, created_at=1.0,
    )
    store.upsert_trace_edge(edge1)
    edge1.weight = 0.8  # 同键覆盖
    store.upsert_trace_edge(edge1)
    edge2 = TraceEdge(
        id="t2", source_concept_id="a", target_concept_id="c", perspective="p2",
        weight=0.5, valence=0.0, last_activated_at=1.0, decay_factor=1.0, created_at=1.0,
    )
    store.upsert_trace_edge(edge2)

    adjacent = store.get_adjacent_traces("a")
    assert len(adjacent) == 2  # 覆盖后不重复
    assert {t.id for t in adjacent} == {"t1", "t2"}
    assert store.get_adjacent_traces("a")[0].weight == 0.8


def test_adjacent_traces_agent_filter(store: ConceptGraphStore) -> None:
    _add_node(store, "a")
    _add_node(store, "b")
    edge = TraceEdge(
        id="t1", source_concept_id="a", target_concept_id="b",
        perspective="agent:silver_wolf", weight=0.5, valence=0.0,
        last_activated_at=1.0, decay_factor=1.0, created_at=1.0,
    )
    store.upsert_trace_edge(edge)
    assert len(store.get_adjacent_traces("a", agent_id="silver_wolf")) == 1
    assert store.get_adjacent_traces("a", agent_id="tighnari") == []


def test_decay_relation_and_trace(store: ConceptGraphStore) -> None:
    _add_node(store, "a")
    _add_node(store, "b")
    store.upsert_relation_edge(RelationEdge(
        id="r1", source_id="a", target_id="b", relation_type="t",
        weight=1.0, created_at=1.0,
    ))
    store.upsert_trace_edge(TraceEdge(
        id="t1", source_concept_id="a", target_concept_id="b", perspective="",
        weight=0.5, valence=0.0, last_activated_at=1.0, decay_factor=1.0, created_at=1.0,
    ))
    result = store.decay_all(relation_factor=0.5, trace_factor=0.5)
    assert result.relation_affected == 1
    assert result.trace_affected == 1
    assert store.get_relation_edges("a")[0].weight == pytest.approx(0.5)
    assert store.get_trace_edges("a")[0].decay_factor == pytest.approx(0.5)


async def test_concept_graph_dual_view(graph: ConceptGraph) -> None:
    """MF-P1-003：写入节点+关系边+Trace 边后双视图同时可查。"""
    graph.add_concept(name="生日")
    graph.add_concept(name="银狼")
    node_a = graph.get_node(graph._id_generator.generate("生日"))
    node_b = graph.get_node(graph._id_generator.generate("银狼"))
    assert node_a is not None and node_b is not None

    graph.add_relation_edge(
        source_id=node_a.id, target_id=node_b.id, relation_type="庆祝",
    )
    graph.add_trace_edge(
        source_id=node_a.id, target_id=node_b.id, perspective="回忆", valence=0.8,
    )

    facts = graph.query_fact_view([node_a.id])
    traces = graph.query_association_view([node_a.id])
    assert len(facts) == 1
    assert len(traces) == 1
    assert facts[0].relation_type == "庆祝"
    assert traces[0].perspective == "回忆"


def test_entity_concept_same_id(graph: ConceptGraph) -> None:
    """MF-P1-002：同名实体与概念 id 相同（同源对齐），type 合并为 BOTH。"""
    entity = graph.add_entity(name="凯文")
    concept = graph.add_concept(name="凯文")
    assert entity.id == concept.id
    assert graph.get_node(entity.id).type == NodeCategory.BOTH


def test_fused_decay_engine_sync_decay(graph: ConceptGraph) -> None:
    """FusedDecayEngine：一次调用同步衰减两层。"""
    node_a = graph.add_concept(name="契约")
    node_b = graph.add_concept(name="琪亚娜")
    graph.add_relation_edge(source_id=node_a.id, target_id=node_b.id, relation_type="绑定")
    graph.add_trace_edge(source_id=node_a.id, target_id=node_b.id, perspective="直觉")

    engine = FusedDecayEngine(graph)
    result = engine.decay(relation_factor=0.8, trace_factor=0.8)
    assert result.relation_affected == 1
    assert result.trace_affected == 1
    facts = graph.query_fact_view([node_a.id])
    traces = graph.query_association_view([node_a.id])
    assert facts[0].weight == pytest.approx(0.8)
    assert traces[0].decay_factor == pytest.approx(0.8)


def test_store_uses_wal_mode(tmp_path: Path) -> None:
    store = ConceptGraphStore(tmp_path)
    try:
        mode = store._conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"
        assert (tmp_path / _DB_FILE).exists()
    finally:
        store.close()


def test_persistence_across_store_reopen(tmp_path: Path) -> None:
    """数据落盘：重建 Store 后数据仍在。"""
    s1 = ConceptGraphStore(tmp_path)
    s1.init_schema()
    s1.upsert_node(ConceptNode(id="n1", name="持久", created_at=1.0, updated_at=1.0))
    s1.upsert_node(ConceptNode(id="n2", name="n2", created_at=1.0, updated_at=1.0))
    s1.close()

    s2 = ConceptGraphStore(tmp_path)
    s2.init_schema()
    try:
        assert s2.get_node_by_id("n1").name == "持久"
        # R07：重开后的内存邻接索引也重建
        s2.upsert_trace_edge(TraceEdge(
            id="t1", source_concept_id="n1", target_concept_id="n2", perspective="",
            weight=0.5, valence=0.0, last_activated_at=1.0, decay_factor=1.0, created_at=1.0,
        ))
        s2.close()

        s3 = ConceptGraphStore(tmp_path)
        s3.init_schema()
        try:
            assert len(s3.get_adjacent_traces("n1")) == 1
        finally:
            s3.close()
    finally:
        s2.close()
