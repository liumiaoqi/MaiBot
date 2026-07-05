"""交互活化集成测试。

验证完整交互流程：情绪驱动触发→影响计算→情绪变化→关系更新→事件持久化→冷却控制。
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.maisaka.agent_interaction.effect_calculator import EffectCalculator
from src.maisaka.agent_interaction.emotion_registry import AgentEmotionManagerRegistry
from src.maisaka.agent_interaction.engine import InteractionEngine
from src.maisaka.agent_interaction.event_store import InteractionEventStore
from src.maisaka.agent_interaction.models import InteractionEventCreate
from src.maisaka.agent_interaction.relationship_manager import AgentRelationshipManager
from src.maisaka.agent_interaction.trigger_base import TriggerEvaluation
from src.maisaka.agent_interaction.cooldown import InteractionCooldownManager, build_agent_pair_key


@pytest.fixture
def mock_emotion_registry():
    """mock情绪注册表，直接操作内存中的情绪状态。"""
    registry = MagicMock(spec=AgentEmotionManagerRegistry)
    _states: dict[str, dict[str, float]] = {}

    def _get_state(agent_id: str):
        state = MagicMock()
        emotions = _states.setdefault(agent_id, {
            "happy": 30, "sad": 10, "anxious": 10,
            "angry": 5, "calm": 40, "excited": 5, "lonely": 70,
        })
        state.emotions = emotions
        dominant = max(emotions, key=emotions.get)
        state.dominant_emotion = dominant
        return state

    def _apply_trigger(agent_id: str, emotion_type: str, delta: float):
        emotions = _states.setdefault(agent_id, {
            "happy": 30, "sad": 10, "anxious": 10,
            "angry": 5, "calm": 40, "excited": 5, "lonely": 70,
        })
        emotions[emotion_type] = max(0, min(100, emotions.get(emotion_type, 0) + delta))

    registry.get_emotion_state = _get_state
    registry.apply_trigger = _apply_trigger
    registry._states = _states
    return registry


@pytest.fixture
def mock_relationship_manager():
    """mock关系管理器。"""
    manager = MagicMock(spec=AgentRelationshipManager)
    _rels: dict[str, dict] = {}

    async def _get_rel(agent_id: str, target_id: str):
        key = f"{agent_id}:{target_id}"
        if key not in _rels:
            return None
        rel = MagicMock()
        rel.relationship_type = _rels[key].get("type", "friend")
        rel.score = _rels[key].get("score", 50)
        return rel

    async def _update_rel(agent_id: str, target_id: str, delta: float):
        key = f"{agent_id}:{target_id}"
        if key not in _rels:
            _rels[key] = {"type": "friend", "score": 50}
        _rels[key]["score"] = max(0, min(1000, _rels[key]["score"] + delta))
        rel = MagicMock()
        rel.relationship_type = _rels[key]["type"]
        rel.score = _rels[key]["score"]
        return rel

    manager.get_relationship = _get_rel
    manager.update_relationship = _update_rel
    manager._rels = _rels

    _rels["silver_wolf:bronya"] = {"type": "friend", "score": 100}
    return manager


@pytest.fixture
def mock_event_store():
    """mock事件存储。"""
    store = MagicMock(spec=InteractionEventStore)
    _events: list[dict] = []

    async def _save(event_data: InteractionEventCreate) -> str:
        event_id = f"ie:{event_data.initiator_agent_id}:{len(_events):x}"
        _events.append({
            "event_id": event_id,
            "initiator_agent_id": event_data.initiator_agent_id,
            "target_agent_id": event_data.target_agent_id,
            "interaction_type": event_data.interaction_type,
            "trigger_reason": event_data.trigger_reason,
            "emotion_effects": event_data.emotion_effects,
            "relationship_effect": event_data.relationship_effect,
            "memory_write_status": event_data.memory_write_status,
            "echo_depth": event_data.echo_depth,
        })
        return event_id

    store.save_event = _save
    store._events = _events
    return store


@pytest.fixture
def engine(mock_emotion_registry, mock_relationship_manager, mock_event_store):
    """创建交互引擎实例（无记忆适配器）。"""
    return InteractionEngine(
        emotion_registry=mock_emotion_registry,
        relationship_manager=mock_relationship_manager,
        event_store=mock_event_store,
    )


class TestEffectCalculator:
    """6.1 验证点：影响计算。"""

    def test_emotion_driven_friend(self):
        calc = EffectCalculator()
        effect = calc.calculate(
            interaction_type="emotion_driven",
            relationship_type="friend",
            initiator_emotion="lonely",
            target_emotion="calm",
        )
        assert not effect.is_empty
        assert "lonely" in effect.initiator_emotion_deltas
        assert effect.initiator_emotion_deltas["lonely"] < 0
        assert effect.relationship_delta > 0

    def test_unknown_type_uses_default_rule(self):
        calc = EffectCalculator()
        effect = calc.calculate(
            interaction_type="nonexistent",
            relationship_type="friend",
            initiator_emotion="calm",
            target_emotion="calm",
        )
        assert not effect.is_empty
        assert "happy" in effect.initiator_emotion_deltas

    def test_echo_decay(self):
        calc = EffectCalculator(echo_decay_ratio=0.5)
        effect_direct = calc.calculate(
            interaction_type="emotion_driven",
            relationship_type="friend",
            initiator_emotion="lonely",
            target_emotion="calm",
            echo_depth=0,
        )
        effect_echo = calc.calculate(
            interaction_type="emotion_driven",
            relationship_type="friend",
            initiator_emotion="lonely",
            target_emotion="calm",
            echo_depth=1,
        )
        for key in effect_direct.initiator_emotion_deltas:
            if key in effect_echo.initiator_emotion_deltas:
                assert abs(effect_echo.initiator_emotion_deltas[key]) <= abs(effect_direct.initiator_emotion_deltas[key])


class TestInteractionEngine:
    """6.1 端到端交互触发验证。"""

    @pytest.mark.asyncio
    async def test_emotion_driven_interaction(self, engine, mock_emotion_registry, mock_event_store):
        evaluation = TriggerEvaluation(
            should_trigger=True,
            trigger_probability=0.8,
            initiator_agent_id="silver_wolf",
            target_agent_id="bronya",
            interaction_type="emotion_driven",
            trigger_reason="银狼感到孤独，想找布洛妮娅",
        )

        result = await engine.execute(evaluation)

        assert result.success
        assert result.event_id != ""
        assert "initiator" in result.emotion_effects
        assert "target" in result.emotion_effects
        assert result.relationship_effect > 0

        wolf_state = mock_emotion_registry.get_emotion_state("silver_wolf")
        assert wolf_state.emotions["lonely"] < 70

        assert len(mock_event_store._events) == 1
        event = mock_event_store._events[0]
        assert event["initiator_agent_id"] == "silver_wolf"
        assert event["target_agent_id"] == "bronya"
        assert event["interaction_type"] == "emotion_driven"

    @pytest.mark.asyncio
    async def test_should_trigger_false_rejected(self, engine):
        evaluation = TriggerEvaluation(
            should_trigger=False,
            trigger_probability=1.0,
            initiator_agent_id="silver_wolf",
            target_agent_id="bronya",
            interaction_type="emotion_driven",
            trigger_reason="不应触发",
        )

        result = await engine.execute(evaluation)
        assert not result.success
        assert "未通过" in result.error

    @pytest.mark.asyncio
    async def test_manual_trigger(self, engine, mock_event_store):
        result = await engine.execute_manual(
            initiator_id="silver_wolf",
            target_id="bronya",
            interaction_type="emotion_driven",
            reason="管理员手动触发",
        )

        assert result.success
        assert "[手动触发]" in mock_event_store._events[0]["trigger_reason"]


class TestCooldownManager:
    """6.1 验证点：冷却控制。"""

    @pytest.mark.asyncio
    async def test_cooldown_blocks_repeat(self):
        with patch("src.maisaka.agent_interaction.cooldown.get_db_session") as mock_session:
            mock_row = MagicMock()
            mock_row.last_interaction_at = datetime.now()
            mock_row.interaction_count_hourly = 1
            mock_row.interaction_count_daily = 1
            mock_row.hourly_reset_at = datetime.now() + timedelta(hours=1)
            mock_row.daily_reset_at = datetime.now() + timedelta(days=1)

            mock_ctx = MagicMock()
            mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
            mock_ctx.__exit__ = MagicMock(return_value=False)
            mock_ctx.execute = MagicMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_row)))
            mock_session.return_value = mock_ctx

            manager = InteractionCooldownManager()
            pair_key = build_agent_pair_key("silver_wolf", "bronya")
            can = await manager.can_trigger(pair_key, cooldown_minutes=30)
            assert not can

    def test_pair_key_ordering(self):
        key1 = build_agent_pair_key("silver_wolf", "bronya")
        key2 = build_agent_pair_key("bronya", "silver_wolf")
        assert key1 == key2


class TestAgentPairKey:
    """验证智能体对键构建。"""

    def test_alphabetical_order(self):
        key = build_agent_pair_key("zebra", "apple")
        assert key == "apple:zebra"

    def test_same_agents(self):
        key = build_agent_pair_key("a", "a")
        assert key == "a:a"


class TestRelationshipUpdate:
    """6.1 验证点：关系分数更新。"""

    @pytest.mark.asyncio
    async def test_positive_interaction_increases_score(self, engine, mock_relationship_manager):
        initial_score = mock_relationship_manager._rels["silver_wolf:bronya"]["score"]

        evaluation = TriggerEvaluation(
            should_trigger=True,
            trigger_probability=0.8,
            initiator_agent_id="silver_wolf",
            target_agent_id="bronya",
            interaction_type="emotion_driven",
            trigger_reason="正面交互",
        )

        result = await engine.execute(evaluation)
        assert result.success
        assert result.relationship_effect > 0

        updated_score = mock_relationship_manager._rels["silver_wolf:bronya"]["score"]
        assert updated_score > initial_score


class TestEventPersistence:
    """6.1 验证点：事件持久化。"""

    @pytest.mark.asyncio
    async def test_event_data_integrity(self, engine, mock_event_store):
        evaluation = TriggerEvaluation(
            should_trigger=True,
            trigger_probability=0.8,
            initiator_agent_id="silver_wolf",
            target_agent_id="bronya",
            interaction_type="emotion_driven",
            trigger_reason="测试事件完整性",
        )

        result = await engine.execute(evaluation)
        assert result.success

        event = mock_event_store._events[0]
        assert event["initiator_agent_id"] == "silver_wolf"
        assert event["target_agent_id"] == "bronya"
        assert event["interaction_type"] == "emotion_driven"
        assert event["trigger_reason"] == "测试事件完整性"
        assert event["relationship_effect"] == result.relationship_effect
        assert event["memory_write_status"] == "skipped"

    @pytest.mark.asyncio
    async def test_echo_depth_recorded(self, engine, mock_event_store):
        evaluation = TriggerEvaluation(
            should_trigger=True,
            trigger_probability=0.8,
            initiator_agent_id="silver_wolf",
            target_agent_id="bronya",
            interaction_type="emotion_driven",
            trigger_reason="回声深度测试",
            metadata={"echo_depth": 2, "echo_parent_event_id": "ie:parent:123"},
        )

        result = await engine.execute(evaluation)
        assert result.success

        event = mock_event_store._events[0]
        assert event["echo_depth"] == 2