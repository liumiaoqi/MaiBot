"""MF-P4-001/004 验收：UnifiedProfileService 统一画像。

对应 tasks.md 7.1：evidence/associations 不同时为空（人物有记忆时）；
valence 加权平均正确；降级策略；LLM 失败 valence=None。
"""

from unittest.mock import AsyncMock

import pytest

from src.A_memorix.core.concept_graph import ConceptGraph, ConceptGraphStore
from src.A_memorix.core.concept_graph.unified_profile_service import UnifiedProfileService


@pytest.fixture
def service(tmp_path) -> UnifiedProfileService:
    store = ConceptGraphStore(tmp_path)
    store.init_schema()
    graph = ConceptGraph(store)
    s = UnifiedProfileService(graph)
    yield s
    store.close()


async def test_profile_with_dual_views(service: UnifiedProfileService) -> None:
    """人物有记忆：evidence + associations + valence 三元组齐备。"""
    person = service._graph.add_entity(name="琪亚娜")
    birthday = service._graph.add_concept(name="生日")
    service._graph.add_relation_edge(
        source_id=person.id, target_id=birthday.id, relation_type="庆祝",
    )
    service._graph.add_trace_edge(
        source_id=person.id, target_id=birthday.id,
        perspective="回忆", weight=0.8, valence=0.7,
    )

    profile = await service.get_person_profile("琪亚娜")
    assert len(profile.evidence) == 1
    assert len(profile.associations) == 1
    assert profile.evidence[0].content == "庆祝: 生日"
    assert profile.associations[0].concept_id == birthday.id
    assert profile.valence == pytest.approx(0.7)


async def test_evidence_missing_associations_remain(service: UnifiedProfileService) -> None:
    """evidence 缺失 → [] + associations 有值。"""
    person = service._graph.add_entity(name="琪亚娜")
    birthday = service._graph.add_concept(name="生日")
    service._graph.add_trace_edge(
        source_id=person.id, target_id=birthday.id, perspective="直觉", weight=0.5, valence=0.3,
    )
    profile = await service.get_person_profile("琪亚娜")
    assert profile.evidence == []
    assert len(profile.associations) == 1


async def test_associations_missing_evidence_remain(service: UnifiedProfileService) -> None:
    """associations 缺失 → [] + evidence 有值。"""
    person = service._graph.add_entity(name="琪亚娜")
    birthday = service._graph.add_concept(name="生日")
    service._graph.add_relation_edge(
        source_id=person.id, target_id=birthday.id, relation_type="庆祝",
    )
    profile = await service.get_person_profile("琪亚娜")
    assert len(profile.evidence) == 1
    assert profile.associations == []


async def test_unknown_person_empty_profile(service: UnifiedProfileService) -> None:
    profile = await service.get_person_profile("不存在的人")
    assert profile.evidence == []
    assert profile.associations == []
    assert profile.valence is None


async def test_valence_weighted_average(service: UnifiedProfileService) -> None:
    """valence = Σ(valence×weight) / Σ(weight)。"""
    person = service._graph.add_entity(name="琪亚娜")
    a = service._graph.add_concept(name="回忆A")
    b = service._graph.add_concept(name="回忆B")
    service._graph.add_trace_edge(source_id=person.id, target_id=a.id, perspective="p1", weight=0.5, valence=1.0)
    service._graph.add_trace_edge(source_id=person.id, target_id=b.id, perspective="p2", weight=1.5, valence=-1.0)
    profile = await service.get_person_profile("琪亚娜")
    expected = (1.0 * 0.5 + (-1.0) * 1.5) / (0.5 + 1.5)
    assert profile.valence == pytest.approx(expected)


async def test_llm_failure_valence_none_or_fallback(service: UnifiedProfileService) -> None:
    """LLM 增强失败 → 降级到加权平均（不崩溃）。"""
    person = service._graph.add_entity(name="琪亚娜")
    a = service._graph.add_concept(name="回忆A")
    service._graph.add_trace_edge(source_id=person.id, target_id=a.id, perspective="p1", weight=0.5, valence=0.8)

    async def _broken_llm(associations):
        raise RuntimeError("LLM 不可用")

    service._llm_valence_enhancer = _broken_llm
    profile = await service.get_person_profile("琪亚娜")
    assert profile.valence == pytest.approx(0.8)  # 加权平均兜底


async def test_llm_valence_override(service: UnifiedProfileService) -> None:
    """LLM 增强成功 → 覆盖加权平均。"""
    person = service._graph.add_entity(name="琪亚娜")
    a = service._graph.add_concept(name="回忆A")
    service._graph.add_trace_edge(source_id=person.id, target_id=a.id, perspective="p1", weight=0.5, valence=0.8)

    service._llm_valence_enhancer = AsyncMock(return_value=-0.5)
    profile = await service.get_person_profile("琪亚娜")
    assert profile.valence == pytest.approx(-0.5)


async def test_derive_profile_compat_signature(service: UnifiedProfileService) -> None:
    """derive_profile 兼容 MemoryServicePort 签名。"""
    person = service._graph.add_entity(name="琪亚娜")
    a = service._graph.add_concept(name="回忆A")
    service._graph.add_trace_edge(source_id=person.id, target_id=a.id, perspective="p1", weight=0.5, valence=0.6)
    result = await service.derive_profile("琪亚娜", observer="silver_wolf")
    assert result["subject"] == "琪亚娜"
    assert result["observer"] == "silver_wolf"
    assert len(result["associations"]) == 1
    assert result["valence"] == pytest.approx(0.6)
