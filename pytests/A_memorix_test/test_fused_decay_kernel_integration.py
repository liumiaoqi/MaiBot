"""MF-P2-005 验收：统一衰减管线（SDKMemoryKernel.maintain_memory → FusedDecayEngine）。

对应 tasks.md 5.4：触发 decay 后概念图事实层关系边权重和联想层 Trace
decay_factor 同步衰减；非 decay 动作仍走原 maintenance 路径。
"""

import pytest

from src.A_memorix.core.runtime.sdk_memory_kernel import SDKMemoryKernel


def _build_kernel(tmp_path) -> SDKMemoryKernel:
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    kernel = SDKMemoryKernel(
        plugin_root=tmp_path,
        config={
            "storage": {"data_dir": str(data_dir)},
            "memory": {"enabled": True, "half_life_hours": 24.0},
        },
    )
    # 模拟 initialize() 后的概念图就绪状态（完整初始化集成在任务 9.2 验证）
    from src.A_memorix.core.concept_graph.concept_graph import ConceptGraph
    from src.A_memorix.core.concept_graph.concept_graph_store import ConceptGraphStore
    from src.A_memorix.core.concept_graph.decay_engine import FusedDecayEngine
    from src.A_memorix.core.concept_graph.unified_id_generator import UnifiedIdGenerator

    store = ConceptGraphStore(data_dir)
    store.init_schema()
    kernel._concept_graph = ConceptGraph(store, UnifiedIdGenerator())
    kernel._fused_decay_engine = FusedDecayEngine(kernel._concept_graph)
    # 短路 initialize：本测试聚焦 decay 委托，完整初始化在任务 9.2 验证
    from unittest.mock import AsyncMock, MagicMock

    kernel._initialized = True
    kernel._apply_runtime_sparse_mode = lambda: None
    kernel._start_background_tasks = AsyncMock()
    maintenance = MagicMock()
    maintenance.maintain_memory = AsyncMock(
        return_value={"success": False, "detail": "未命中可维护关系"},
    )
    kernel._maintenance_service = maintenance
    return kernel


def _prepare_graph_with_edges(kernel: SDKMemoryKernel) -> str:
    """写入节点 + 关系边 + Trace 边，返回源节点 id。"""
    graph = kernel._concept_graph
    assert graph is not None
    node_a = graph.add_concept(name="契约")
    node_b = graph.add_concept(name="琪亚娜")
    graph.add_relation_edge(source_id=node_a.id, target_id=node_b.id, relation_type="绑定")
    graph.add_trace_edge(source_id=node_a.id, target_id=node_b.id, perspective="直觉", valence=0.6)
    return node_a.id


@pytest.mark.asyncio
async def test_maintain_memory_decay_syncs_dual_projection(tmp_path) -> None:
    """maintain_memory(decay) → 事实层与联想层同步衰减（同一 factor）。"""
    kernel = _build_kernel(tmp_path)
    node_a = _prepare_graph_with_edges(kernel)
    graph = kernel._concept_graph
    assert graph is not None

    before_facts = graph.query_fact_view([node_a])
    before_traces = graph.query_association_view([node_a])
    assert before_facts[0].weight == pytest.approx(1.0)
    assert before_traces[0].decay_factor == pytest.approx(1.0)

    # 24h 半衰期，12h 衰减 → factor = 0.5^0.5 ≈ 0.7071
    result = await kernel.maintain_memory(action="decay", hours=12.0)
    assert result["success"] is True
    assert result["relation_affected"] == 1
    assert result["trace_affected"] == 1

    after_facts = graph.query_fact_view([node_a])
    after_traces = graph.query_association_view([node_a])
    assert after_facts[0].weight == pytest.approx(0.5 ** 0.5, rel=1e-3)
    assert after_traces[0].decay_factor == pytest.approx(0.5 ** 0.5, rel=1e-3)


@pytest.mark.asyncio
async def test_maintain_memory_decay_default_hours(tmp_path) -> None:
    """hours 缺省 → 1 小时衰减（factor = 0.5^(1/24) ≈ 0.9715）。"""
    kernel = _build_kernel(tmp_path)
    node_a = _prepare_graph_with_edges(kernel)
    result = await kernel.maintain_memory(action="decay")
    assert result["success"] is True
    graph = kernel._concept_graph
    after_facts = graph.query_fact_view([node_a])
    assert after_facts[0].weight == pytest.approx(0.5 ** (1.0 / 24.0), rel=1e-3)


@pytest.mark.asyncio
async def test_maintain_memory_non_decay_keeps_original_path(tmp_path) -> None:
    """非 decay 动作仍走原 maintenance 路径（未命中关系 → 失败语义不变）。"""
    kernel = _build_kernel(tmp_path)
    result = await kernel.maintain_memory(action="reinforce", target="nonexistent")
    assert result["success"] is False
