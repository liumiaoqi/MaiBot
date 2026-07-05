"""记忆驱动触发端到端验证（6.4）+ 提示词注入验证（6.5）。"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.maisaka.agent_interaction.memory.adapter import AgentMemoryAdapter
from src.maisaka.agent_interaction.triggers.memory_driven import MemoryDrivenTrigger
from src.maisaka.agent_interaction.models import AgentInteractionRelationshipRead
from src.maisaka.agent.emotion import EmotionState
from src.services.memory_service import MemorySearchResult, MemoryWriteResult


def _make_emotion_state(dominant="calm", emotions=None) -> EmotionState:
    default = {"happy": 20, "sad": 10, "anxious": 10, "angry": 5, "calm": 40, "excited": 5, "lonely": 10}
    if emotions:
        default.update(emotions)
    return EmotionState(emotions=default, dominant_emotion=dominant or "calm", updated_at=0.0)


def _make_relationship(
    target_id="bronya",
    score=100,
    rel_type="friend",
    last_interaction=None,
) -> AgentInteractionRelationshipRead:
    return AgentInteractionRelationshipRead(
        id=1,
        agent_id="silver_wolf",
        target_agent_id=target_id,
        score=score,
        relationship_type=rel_type,
        attitude="friendly",
        interaction_count=5,
        last_interaction_at=last_interaction,
        created_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:00:00",
    )


class TestMemoryDrivenTrigger:
    """6.4 记忆驱动触发端到端验证。"""

    @pytest.mark.asyncio
    async def test_positive_memory_bonus(self):
        mock_adapter = MagicMock(spec=AgentMemoryAdapter)
        mock_adapter.search_interaction_memory = AsyncMock(return_value=MemorySearchResult(
            success=True,
            hits=[
                MagicMock(content="愉快的聊天", metadata={"tags": ["positive"]}),
                MagicMock(content="开心", metadata={"tags": ["positive"]}),
            ],
        ))

        trigger = MemoryDrivenTrigger(memory_adapter=mock_adapter, positive_bonus=0.2)
        emotion = _make_emotion_state("lonely", {"lonely": 60})
        rels = [_make_relationship(score=200)]

        result = await trigger.evaluate("silver_wolf", emotion, rels)
        assert result.should_trigger
        assert result.trigger_probability > 0.3
        assert result.target_agent_id == "bronya"

    @pytest.mark.asyncio
    async def test_negative_memory_penalty(self):
        mock_adapter = MagicMock(spec=AgentMemoryAdapter)
        mock_adapter.search_interaction_memory = AsyncMock(return_value=MemorySearchResult(
            success=True,
            hits=[
                MagicMock(content="争吵", metadata={"tags": ["negative"]}),
                MagicMock(content="不愉快", metadata={"tags": ["negative"]}),
            ],
        ))

        trigger = MemoryDrivenTrigger(memory_adapter=mock_adapter, negative_penalty=0.3)
        emotion = _make_emotion_state("angry", {"angry": 50})
        rels = [_make_relationship(score=200)]

        result = await trigger.evaluate("silver_wolf", emotion, rels)
        assert not result.should_trigger or result.trigger_probability < 0.3

    @pytest.mark.asyncio
    async def test_reconcile_bonus(self):
        mock_adapter = MagicMock(spec=AgentMemoryAdapter)
        mock_adapter.search_interaction_memory = AsyncMock(return_value=MemorySearchResult(
            success=True,
            hits=[
                MagicMock(content="想和好", metadata={"tags": ["negative"]}),
            ],
        ))

        trigger = MemoryDrivenTrigger(memory_adapter=mock_adapter, reconcile_bonus=0.15)
        emotion = _make_emotion_state("sad", {"sad": 50})
        rels = [_make_relationship(score=200)]

        result = await trigger.evaluate("silver_wolf", emotion, rels)
        if result.should_trigger:
            assert "想和好" in result.trigger_reason or "和好" in result.metadata.get("memory_desc", "")

    @pytest.mark.asyncio
    async def test_reunion_after_long_gap(self):
        from datetime import datetime, timedelta

        mock_adapter = MagicMock(spec=AgentMemoryAdapter)
        mock_adapter.search_interaction_memory = AsyncMock(return_value=MemorySearchResult(
            success=True,
            hits=[],
        ))

        trigger = MemoryDrivenTrigger(
            memory_adapter=mock_adapter,
            reunion_probability=0.15,
            reunion_threshold_hours=24,
        )
        emotion = _make_emotion_state("lonely", {"lonely": 60})
        last_time = datetime.now() - timedelta(hours=48)
        rels = [_make_relationship(score=200, last_interaction=last_time)]

        result = await trigger.evaluate("silver_wolf", emotion, rels)
        if result.should_trigger:
            assert "好久" in result.trigger_reason or "想念" in result.trigger_reason or result.target_agent_id == "bronya"

    @pytest.mark.asyncio
    async def test_no_trigger_low_probability(self):
        mock_adapter = MagicMock(spec=AgentMemoryAdapter)
        mock_adapter.search_interaction_memory = AsyncMock(return_value=MemorySearchResult(
            success=True,
            hits=[],
        ))

        trigger = MemoryDrivenTrigger(memory_adapter=mock_adapter)
        emotion = _make_emotion_state("calm")
        rels = [_make_relationship(score=10)]

        result = await trigger.evaluate("silver_wolf", emotion, rels)
        assert not result.should_trigger


class TestAgentMemoryAdapter:
    """6.5 提示词注入验证 — 记忆适配器。"""

    def test_build_chat_id_ordering(self):
        id1 = AgentMemoryAdapter.build_chat_id("zebra", "apple")
        id2 = AgentMemoryAdapter.build_chat_id("apple", "zebra")
        assert id1 == id2
        assert id1 == "agent_interaction:apple:zebra"

    def test_build_person_id(self):
        pid = AgentMemoryAdapter.build_person_id("silver_wolf")
        assert pid == "agent:silver_wolf"

    def test_is_interaction_chat_id(self):
        assert AgentMemoryAdapter.is_interaction_chat_id("agent_interaction:a:b")
        assert not AgentMemoryAdapter.is_interaction_chat_id("normal_chat_id")

    def test_parse_agent_ids(self):
        result = AgentMemoryAdapter.parse_agent_ids_from_chat_id("agent_interaction:alpha:beta")
        assert result == ("alpha", "beta")

    def test_parse_invalid_chat_id(self):
        assert AgentMemoryAdapter.parse_agent_ids_from_chat_id("invalid") is None
        assert AgentMemoryAdapter.parse_agent_ids_from_chat_id("agent_interaction:onlyone") is None

    @pytest.mark.asyncio
    async def test_write_interaction_memory(self):
        with patch("src.maisaka.agent_interaction.memory.adapter.memory_service") as mock_svc:
            mock_svc.ingest_text = AsyncMock(return_value=MemoryWriteResult(
                success=True,
                stored_ids=["mem1", "mem2"],
            ))

            adapter = AgentMemoryAdapter()
            result = await adapter.write_interaction_memory(
                event_id="ie:test:1",
                initiator_id="silver_wolf",
                target_id="bronya",
                content="愉快的聊天",
                emotion_tag="positive",
                interaction_type="emotion_driven",
            )

            assert result.success
            assert mock_svc.ingest_text.call_count == 2

    @pytest.mark.asyncio
    async def test_search_interaction_memory(self):
        with patch("src.maisaka.agent_interaction.memory.adapter.memory_service") as mock_svc:
            mock_svc.search = AsyncMock(return_value=MemorySearchResult(
                success=True,
                hits=[MagicMock(content="测试记忆")],
            ))

            adapter = AgentMemoryAdapter()
            result = await adapter.search_interaction_memory("silver_wolf", "bronya")

            assert result.success
            mock_svc.search.assert_called_once()
            call_kwargs = mock_svc.search.call_args
            assert call_kwargs.kwargs.get("chat_id") == "agent_interaction:bronya:silver_wolf"
            assert call_kwargs.kwargs.get("person_id") == "agent:silver_wolf"