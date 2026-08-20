"""P0-1 回声传播共享状态测试 — 回声路径复用主引擎共享组件。

覆盖 spec 5.4.1-1~3 + 4.1 None 出声：
- 组件实例同一性（assert is）
- 回声基于真实共享状态传播 + 事件流落库（echo_depth>=1 + echo_parent_event_id）
- 组件缺省时 _propagate_echo logger.error 且不执行（静默失效禁令）
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.maisaka.agent_interaction.echo_detector import EchoDetector
from src.maisaka.agent_interaction.emotion_registry import AgentEmotionManagerRegistry
from src.maisaka.agent_interaction.engine import InteractionEngine, InteractionResult
from src.maisaka.agent_interaction.event_store import InteractionEventStore
from src.maisaka.agent_interaction.models import InteractionEventCreate
from src.maisaka.agent_interaction.relationship_manager import AgentRelationshipManager
from src.maisaka.agent_interaction.trigger_base import TriggerEvaluation


def _make_mock_registry() -> MagicMock:
    """mock 情绪注册表（预置状态，可 apply_trigger 变更）。"""
    registry = MagicMock(spec=AgentEmotionManagerRegistry)
    _states: dict[str, dict[str, float]] = {}

    def _get_state(agent_id: str):
        state = MagicMock()
        emotions = _states.setdefault(agent_id, {"happy": 30, "sad": 10, "lonely": 70})
        state.emotions = emotions
        state.dominant_emotion = max(emotions, key=emotions.get)
        return state

    def _apply_trigger(agent_id: str, emotion_type: str, delta: float):
        emotions = _states.setdefault(agent_id, {"happy": 30, "sad": 10, "lonely": 70})
        emotions[emotion_type] = max(0, min(100, emotions.get(emotion_type, 0) + delta))

    registry.get_emotion_state = _get_state
    registry.apply_trigger = _apply_trigger
    registry._states = _states
    return registry


def _make_mock_relationship_manager() -> MagicMock:
    """mock 关系管理器。"""
    manager = MagicMock(spec=AgentRelationshipManager)

    async def _get_rel(agent_id: str, target_id: str):
        rel = MagicMock()
        rel.relationship_type = "friend"
        rel.score = 50
        return rel

    manager.get_relationship = _get_rel
    manager.update_relationship = AsyncMock()
    return manager


def _make_mock_event_store() -> MagicMock:
    """mock 事件存储（记录保存的事件）。"""
    store = MagicMock(spec=InteractionEventStore)
    _events: list[dict] = []

    async def _save(event_data: InteractionEventCreate) -> str:
        event_id = f"ie:test:{len(_events):x}"
        _events.append(
            {
                "event_id": event_id,
                "echo_depth": event_data.echo_depth,
                "echo_parent_event_id": event_data.echo_parent_event_id,
                "initiator_agent_id": event_data.initiator_agent_id,
                "target_agent_id": event_data.target_agent_id,
            }
        )
        return event_id

    store.save_event = _save
    store._events = _events
    return store


def _big_echo_result(event_id: str = "ev:main:1") -> InteractionResult:
    """构造触发回声的结果：单一情绪变化量 > 20。"""
    return InteractionResult(
        success=True,
        event_id=event_id,
        emotion_effects={"initiator": {"lonely": -30}, "target": {"happy": 35}},
        relationship_effect=5.0,
    )


def _evaluation() -> TriggerEvaluation:
    """构造交互评估（深度 0 起回声）。"""
    return TriggerEvaluation(
        should_trigger=True,
        trigger_probability=0.8,
        initiator_agent_id="agent_a",
        target_agent_id="agent_b",
        interaction_type="emotion_driven",
        trigger_reason="测试回声",
    )


class TestEchoSharedState:
    """P0-1 回声共享状态：同一组件实例 + 真实状态传播。"""

    def test_engine_injects_shared_components(self) -> None:
        """InteractionEngine 装配的 EchoDetector 与主引擎共享同一组件实例。"""
        registry = _make_mock_registry()
        rel_manager = _make_mock_relationship_manager()
        event_store = _make_mock_event_store()
        engine = InteractionEngine(
            emotion_registry=registry,
            relationship_manager=rel_manager,
            event_store=event_store,
        )
        assert engine._echo_detector._emotion_registry is registry
        assert engine._echo_detector._relationship_manager is rel_manager
        assert engine._echo_detector._event_store is event_store

    @pytest.mark.asyncio
    async def test_none_components_log_error_and_skip(self, caplog: object) -> None:
        """组件缺省（None）→ 回声不执行（不建空引擎）且打 error 日志。"""
        detector = EchoDetector(echo_max_depth=3, echo_decay_ratio=0.5)
        result = _big_echo_result()
        evaluation = _evaluation()
        with caplog.at_level("ERROR", logger="src.maisaka.agent_interaction.echo_detector"):
            await detector.check_and_propagate(result, evaluation)
        assert any("回声传播组件缺失" in rec.message for rec in caplog.records), \
            "组件缺失时必须打 error 日志（静默失效禁令）"

    @pytest.mark.asyncio
    async def test_echo_persists_event_with_depth(self) -> None:
        """真实回声传播：共享 event_store 落库事件 echo_depth>=1 + echo_parent_event_id 正确。"""
        registry = _make_mock_registry()
        rel_manager = _make_mock_relationship_manager()
        event_store = _make_mock_event_store()
        engine = InteractionEngine(
            emotion_registry=registry,
            relationship_manager=rel_manager,
            event_store=event_store,
        )
        # 主交互成功产生回声事件（不 mock _propagate_echo——走真实传播路径）
        await engine._echo_detector.check_and_propagate(
            _big_echo_result(event_id="ev:main:1"), _evaluation()
        )
        assert len(event_store._events) == 1
        event = event_store._events[0]
        assert event["echo_depth"] >= 1
        assert event["echo_parent_event_id"] == "ev:main:1"

    @pytest.mark.asyncio
    async def test_echo_mutates_shared_state(self) -> None:
        """回声执行对共享 registry 产生真实情绪变更（非空状态上执行）。"""
        registry = _make_mock_registry()
        registry._states.setdefault("agent_a", {"happy": 30, "lonely": 70})
        rel_manager = _make_mock_relationship_manager()
        event_store = _make_mock_event_store()
        engine = InteractionEngine(
            emotion_registry=registry,
            relationship_manager=rel_manager,
            event_store=event_store,
        )
        # 回声在共享 registry 上执行：回声交互会 apply_trigger 修改真实状态
        await engine._echo_detector.check_and_propagate(
            _big_echo_result(), _evaluation()
        )
        # 回声交互在共享 registry 上落地情绪变更（初始 happy=30，回声后值变化）
        agent_a_state = registry._states["agent_a"]
        assert agent_a_state["happy"] != 30 or agent_a_state["lonely"] != 70, \
            "回声必须对共享 registry 产生真实情绪变更（非空状态上执行）"
