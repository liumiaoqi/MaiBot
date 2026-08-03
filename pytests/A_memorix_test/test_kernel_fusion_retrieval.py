"""MF-P3-004/005/006 验收：SDKMemoryKernel 检索路径融合替换。

对应 tasks.md 6.3：FUSION_FULL 时 search_memory/recall_with_intuition 走
SpreadAnchorRetriever；FUSION_OFF 走原路径；HeuristicInjector 调用方式不变。
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.A_memorix.core.runtime.sdk_memory_kernel import SDKMemoryKernel


def _build_kernel(tmp_path, stage: str = "fusion_off") -> SDKMemoryKernel:
    kernel = SDKMemoryKernel(
        plugin_root=tmp_path,
        config={"memory_fusion": {"stage": stage}},
    )
    kernel._initialized = True
    kernel._apply_runtime_sparse_mode = lambda: None
    kernel._start_background_tasks = AsyncMock()
    kernel._search_service = MagicMock()
    kernel._search_service.search_memory = AsyncMock(
        return_value={"summary": "", "hits": [{"content": "原路径"}], "filtered": False},
    )
    return kernel


def _inject_fusion(kernel: SDKMemoryKernel, tmp_path) -> None:
    """注入概念图 + 融合检索器（模拟 initialize 后状态）。"""
    from src.A_memorix.core.concept_graph.concept_graph import ConceptGraph
    from src.A_memorix.core.concept_graph.concept_graph_store import ConceptGraphStore
    from src.A_memorix.core.concept_graph.spread_anchor_retriever import SpreadAnchorRetriever

    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    store = ConceptGraphStore(data_dir)
    store.init_schema()
    graph = ConceptGraph(store)
    birthday = graph.add_concept(name="生日")
    kiana = graph.add_concept(name="琪亚娜")
    graph.add_trace_edge(source_id=birthday.id, target_id=kiana.id, perspective="回忆", weight=0.8)
    kernel._concept_graph = graph
    kernel._fusion_retriever = SpreadAnchorRetriever(graph)


@pytest.mark.asyncio
async def test_fusion_off_keeps_original_search_path(tmp_path) -> None:
    """FUSION_OFF：search_memory 走原路径。"""
    kernel = _build_kernel(tmp_path, stage="fusion_off")
    from src.A_memorix.core.runtime.services.types import KernelSearchRequest

    result = await kernel.search_memory(KernelSearchRequest(query="生日", limit=5))
    assert result["hits"] == [{"content": "原路径"}]


@pytest.mark.asyncio
async def test_fusion_full_search_uses_retriever(tmp_path) -> None:
    """FUSION_FULL：search_memory 走扩散-锚定。"""
    kernel = _build_kernel(tmp_path, stage="fusion_full")
    _inject_fusion(kernel, tmp_path)
    from src.A_memorix.core.runtime.services.types import KernelSearchRequest

    result = await kernel.search_memory(KernelSearchRequest(query="生日", limit=5))
    assert result["hits"]
    names = {hit["content"] for hit in result["hits"]}
    assert "生日" in names
    assert "琪亚娜" in names  # 扩散命中
    assert result["hits"][0]["metadata"]["anchor_status"] == "anchored"


def test_fusion_full_recall_with_intuition_uses_retriever(tmp_path) -> None:
    """FUSION_FULL：recall_with_intuition 走融合检索。"""
    kernel = _build_kernel(tmp_path, stage="fusion_full")
    _inject_fusion(kernel, tmp_path)
    result = kernel.recall_with_intuition(
        seeds=["生日"], context_text="回忆", agent_id="silver_wolf",
    )
    assert result["recall_items"]
    assert result["recall_items"][0]["concept_name"] == "生日"


def test_fusion_off_recall_delegates_to_memory_field(tmp_path) -> None:
    """FUSION_OFF：recall_with_intuition 委托 memory_field。"""
    kernel = _build_kernel(tmp_path, stage="fusion_off")
    field = MagicMock()
    field.recall_with_intuition.return_value = {"recall_items": [], "intuition": None}
    kernel._memory_field = field
    result = kernel.recall_with_intuition(
        seeds=["生日"], context_text="回忆", agent_id="silver_wolf",
    )
    field.recall_with_intuition.assert_called_once()
    assert result == {"recall_items": [], "intuition": None}


@pytest.mark.asyncio
async def test_fusion_full_profile_uses_unified_service(tmp_path) -> None:
    """FUSION_FULL：get_person_profile 走 UnifiedProfileService（三元组）。"""
    from src.A_memorix.core.concept_graph.unified_profile_service import UnifiedProfileService

    kernel = _build_kernel(tmp_path, stage="fusion_full")
    _inject_fusion(kernel, tmp_path)
    kernel._unified_profile_service = UnifiedProfileService(kernel._concept_graph)

    person = kernel._concept_graph.add_entity(name="凯文")
    concept = kernel._concept_graph.add_concept(name="终焉")
    kernel._concept_graph.add_relation_edge(source_id=person.id, target_id=concept.id, relation_type="对抗")
    kernel._concept_graph.add_trace_edge(source_id=person.id, target_id=concept.id, perspective="回忆", weight=0.8, valence=0.7)

    result = await kernel.get_person_profile(person_id="凯文", limit=4)
    assert len(result["evidence"]) == 1
    assert len(result["associations"]) == 1
    assert result["valence"] == pytest.approx(0.7)
    assert result["evidence"][0]["content"] == "对抗: 终焉"  # 原字段语义不变


@pytest.mark.asyncio
async def test_fusion_off_profile_keeps_facade(tmp_path) -> None:
    """FUSION_OFF：get_person_profile 走原 PersonProfileFacade。"""
    kernel = _build_kernel(tmp_path, stage="fusion_off")
    facade = MagicMock()
    facade.get_person_profile = AsyncMock(return_value={"person_id": "x", "evidence": []})
    kernel._person_profile_facade = facade
    result = await kernel.get_person_profile(person_id="x", limit=4)
    assert result["person_id"] == "x"
    facade.get_person_profile.assert_called_once()
