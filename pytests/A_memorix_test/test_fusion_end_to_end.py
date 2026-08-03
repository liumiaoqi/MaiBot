"""DFX 4.2 验收：融合端到端（FUSION_FULL 全链路）。

对应 tasks.md 10.4：
- observe_experience → 概念图写入 → search → 融合结果（事实+联想）
- ingest_summary → 概念图写入 → get_person_profile → 统一画像
- maintain_memory(decay) → 事实层和联想层同步衰减
"""

from unittest.mock import AsyncMock

import pytest

from src.A_memorix.core.concept_graph.concept_graph import ConceptGraph
from src.A_memorix.core.concept_graph.concept_graph_store import ConceptGraphStore
from src.A_memorix.core.concept_graph.fused_write_pipeline import FusedWritePipeline
from src.A_memorix.core.concept_graph.fusion_config import FusionConfig
from src.A_memorix.core.concept_graph.fusion_router import FusionRouter
from src.A_memorix.core.concept_graph.spread_anchor_retriever import SpreadAnchorRetriever
from src.A_memorix.core.concept_graph.unified_profile_service import UnifiedProfileService


class _FusionEnvironment:
    """模拟 kernel FUSION_FULL 集成环境。"""

    def __init__(self, tmp_path) -> None:
        data_dir = tmp_path / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        self.store = ConceptGraphStore(data_dir)
        self.store.init_schema()
        self.graph = ConceptGraph(self.store)
        self.pipeline = FusedWritePipeline(self.graph, self.store)
        self.retriever = SpreadAnchorRetriever(self.graph)
        self.profile_service = UnifiedProfileService(self.graph)
        self.router = FusionRouter(
            config=FusionConfig({"stage": "fusion_full"}),
            retriever=self.retriever,
            profile_service=self.profile_service,
        )


async def _observe(env: _FusionEnvironment, text: str, agent_id: str, source_id: str) -> None:
    """observe 经概念提取（注入）写入概念图。"""
    extractor = AsyncMock(return_value=["生日", "琪亚娜"])
    env.pipeline._concept_extractor = extractor
    request = type("Req", (), {
        "text": text,
        "agent_id": agent_id,
        "source_id": source_id,
        "valence": 0.5,
    })()
    result = await env.pipeline.observe_experience(request)
    assert result.success is True


@pytest.mark.asyncio
async def test_observe_search_profile_decay_end_to_end(tmp_path) -> None:
    """端到端：observe → search（融合结果）→ profile（三元组）→ decay（同步衰减）。"""
    env = _FusionEnvironment(tmp_path)

    # 1. observe 写入概念图（双投影：节点 + 联想 trace）
    await _observe(env, "今天是琪亚娜的生日", "silver_wolf", "obs-1")
    birthday = env.graph._store.get_node_by_name("生日")
    kiana = env.graph._store.get_node_by_name("琪亚娜")
    assert birthday is not None and kiana is not None

    # 2. search：融合检索返回事实锚点 + 联想扩散
    result = await env.router.search("生日", agent_id="silver_wolf", limit=5)
    assert result.anchor_status.value == "anchored"
    names = {item.context for item in result.items}
    assert "生日" in names
    assert "琪亚娜" in names  # 联想扩散命中

    # 3. get_person_profile：统一画像三元组
    profile = await env.router.get_person_profile("琪亚娜", agent_id="silver_wolf", limit=4)
    assert len(profile["associations"]) == 1
    assert profile["valence"] is not None

    # 4. decay：事实层 + 联想层同步衰减（经 FusedDecayEngine）
    from src.A_memorix.core.concept_graph.decay_engine import FusedDecayEngine

    engine = FusedDecayEngine(env.graph)
    result = engine.decay(relation_factor=0.5, trace_factor=0.5)
    assert result.relation_affected == 0  # observe 只写 trace（无关系边）
    assert result.trace_affected >= 1
    traces = env.graph.query_association_view([birthday.id])
    assert traces[0].decay_factor == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_ingest_profile_end_to_end(tmp_path) -> None:
    """端到端：ingest_summary → 概念图 → get_person_profile → 统一画像。"""
    env = _FusionEnvironment(tmp_path)
    env.pipeline._concept_extractor = AsyncMock(return_value=["契约", "终焉"])

    result = await env.pipeline.ingest_summary(
        external_id="ext-1", chat_id="chat-1", text="契约与终焉的故事", agent_id="tighnari",
    )
    assert result["success"] is True

    profile = await env.router.get_person_profile("契约", agent_id="tighnari", limit=4)
    # ingest 写节点（无 trace）→ evidence 空 + associations 空（无联想数据），画像仍返回
    assert profile["person_id"] == "契约"
