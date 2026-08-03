"""MF-M-001/002 验收：FusionRouter 按 stage 路由。

对应 tasks.md 8.2：FUSION_OFF 走原路径回调；FUSION_FULL 走融合路径。
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.A_memorix.core.concept_graph import (
    AnchorStatus,
    ConceptGraph,
    ConceptGraphStore,
)
from src.A_memorix.core.concept_graph.fusion_config import FusionConfig
from src.A_memorix.core.concept_graph.fusion_router import FusionRouter
from src.A_memorix.core.concept_graph.spread_anchor_retriever import SpreadAnchorRetriever
from src.A_memorix.core.concept_graph.unified_profile_service import UnifiedProfileService


def _build_router(stage: str, tmp_path) -> FusionRouter:
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    store = ConceptGraphStore(data_dir)
    store.init_schema()
    graph = ConceptGraph(store)
    return FusionRouter(
        config=FusionConfig({"stage": stage}),
        retriever=SpreadAnchorRetriever(graph),
        profile_service=UnifiedProfileService(graph),
        legacy_search=AsyncMock(return_value=MagicMock(success=True)),
        legacy_get_person_profile=AsyncMock(return_value={"person_id": "x"}),
        legacy_build_profile_injection_text=AsyncMock(return_value="legacy injection"),
    )


@pytest.mark.asyncio
async def test_fusion_off_routes_to_legacy(tmp_path) -> None:
    router = _build_router("fusion_off", tmp_path)
    result = await router.search("生日")
    assert result.success is True
    profile = await router.get_person_profile("琪亚娜")
    assert profile["person_id"] == "x"
    text = await router.build_profile_injection_text("琪亚娜")
    assert text == "legacy injection"


@pytest.mark.asyncio
async def test_fusion_full_uses_fusion_paths(tmp_path) -> None:
    router = _build_router("fusion_full", tmp_path)
    # 写入融合数据
    graph = router._retriever._graph
    person = graph.add_entity(name="琪亚娜")
    birthday = graph.add_concept(name="生日")
    graph.add_relation_edge(source_id=person.id, target_id=birthday.id, relation_type="庆祝")
    graph.add_trace_edge(source_id=person.id, target_id=birthday.id, perspective="回忆", weight=0.8, valence=0.6)

    result = await router.search("生日", limit=5)
    assert result.anchor_status == AnchorStatus.ANCHORED
    assert result.items

    profile = await router.get_person_profile("琪亚娜", limit=4)
    assert len(profile["evidence"]) == 1
    assert len(profile["associations"]) == 1
    assert profile["valence"] == pytest.approx(0.6)

    text = await router.build_profile_injection_text("琪亚娜")
    assert "庆祝: 生日" in text


@pytest.mark.asyncio
async def test_fusion_off_without_legacy_raises(tmp_path) -> None:
    """FUSION_OFF 且未注入 legacy 回调 → 显式报错（不静默）。"""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    store = ConceptGraphStore(data_dir)
    store.init_schema()
    graph = ConceptGraph(store)
    router = FusionRouter(
        config=FusionConfig({"stage": "fusion_off"}),
        retriever=SpreadAnchorRetriever(graph),
        profile_service=UnifiedProfileService(graph),
    )
    with pytest.raises(RuntimeError, match="legacy_search"):
        await router.search("生日")
