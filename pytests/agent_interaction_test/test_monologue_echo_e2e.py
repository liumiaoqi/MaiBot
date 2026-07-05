"""内心独白端到端验证（6.2）+ 交互回声端到端验证（6.3）。"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.maisaka.agent_interaction.echo_detector import EchoDetector
from src.maisaka.agent_interaction.engine import InteractionResult
from src.maisaka.agent_interaction.trigger_base import TriggerEvaluation
from src.maisaka.agent_interaction.monologue_trigger import MonologueTrigger


class TestEchoDetector:
    """6.3 交互回声端到端验证。"""

    def test_loop_detection(self):
        chain = ["agent_a", "agent_b"]
        assert EchoDetector._detect_loop(chain, "agent_a") is True
        assert EchoDetector._detect_loop(chain, "agent_c") is False

    def test_loop_detection_empty_chain(self):
        assert EchoDetector._detect_loop([], "agent_a") is False

    @pytest.mark.asyncio
    async def test_no_echo_below_threshold(self):
        detector = EchoDetector(echo_max_depth=3, echo_decay_ratio=0.5)
        result = InteractionResult(
            success=True,
            event_id="ie:test:1",
            emotion_effects={
                "initiator": {"happy": 5},
                "target": {"calm": -3},
            },
            relationship_effect=2.0,
        )
        evaluation = TriggerEvaluation(
            should_trigger=True,
            initiator_agent_id="agent_a",
            target_agent_id="agent_b",
            interaction_type="emotion_driven",
            trigger_reason="低强度交互",
        )

        with patch.object(detector, "_propagate_echo", new_callable=AsyncMock) as mock_prop:
            await detector.check_and_propagate(result, evaluation)
            mock_prop.assert_not_called()

    @pytest.mark.asyncio
    async def test_echo_triggered_above_threshold(self):
        detector = EchoDetector(echo_max_depth=3, echo_decay_ratio=0.5)
        result = InteractionResult(
            success=True,
            event_id="ie:test:2",
            emotion_effects={
                "initiator": {"lonely": -25},
                "target": {"happy": 30},
            },
            relationship_effect=5.0,
        )
        evaluation = TriggerEvaluation(
            should_trigger=True,
            trigger_probability=0.8,
            initiator_agent_id="agent_a",
            target_agent_id="agent_b",
            interaction_type="emotion_driven",
            trigger_reason="高强度交互",
        )

        with patch.object(detector, "_propagate_echo", new_callable=AsyncMock) as mock_prop:
            await detector.check_and_propagate(result, evaluation)
            mock_prop.assert_called_once()
            echo_eval = mock_prop.call_args[0][0]
            assert echo_eval.initiator_agent_id == "agent_b"
            assert echo_eval.target_agent_id == "agent_a"
            assert echo_eval.metadata["echo_depth"] == 1

    @pytest.mark.asyncio
    async def test_echo_max_depth_truncation(self):
        detector = EchoDetector(echo_max_depth=3, echo_decay_ratio=0.5)
        result = InteractionResult(
            success=True,
            event_id="ie:test:3",
            emotion_effects={
                "initiator": {"lonely": -25},
                "target": {"happy": 30},
            },
            relationship_effect=5.0,
        )
        evaluation = TriggerEvaluation(
            should_trigger=True,
            trigger_probability=0.8,
            initiator_agent_id="agent_a",
            target_agent_id="agent_b",
            interaction_type="emotion_driven",
            trigger_reason="深度3回声",
            metadata={"echo_depth": 3},
        )

        with patch.object(detector, "_propagate_echo", new_callable=AsyncMock) as mock_prop:
            await detector.check_and_propagate(result, evaluation)
            mock_prop.assert_not_called()

    @pytest.mark.asyncio
    async def test_echo_loop_detection_truncation(self):
        detector = EchoDetector(echo_max_depth=3, echo_decay_ratio=0.5)
        result = InteractionResult(
            success=True,
            event_id="ie:test:4",
            emotion_effects={
                "initiator": {"lonely": -25},
                "target": {"happy": 30},
            },
            relationship_effect=5.0,
        )
        evaluation = TriggerEvaluation(
            should_trigger=True,
            trigger_probability=0.8,
            initiator_agent_id="agent_a",
            target_agent_id="agent_c",
            interaction_type="emotion_driven",
            trigger_reason="环路检测",
            metadata={"echo_chain": ["agent_a", "agent_b", "agent_c"]},
        )

        with patch.object(detector, "_propagate_echo", new_callable=AsyncMock) as mock_prop:
            await detector.check_and_propagate(result, evaluation)
            mock_prop.assert_not_called()

    @pytest.mark.asyncio
    async def test_echo_decay_probability(self):
        detector = EchoDetector(echo_max_depth=3, echo_decay_ratio=0.5)
        result = InteractionResult(
            success=True,
            event_id="ie:test:5",
            emotion_effects={
                "initiator": {"lonely": -25},
                "target": {"happy": 30},
            },
            relationship_effect=5.0,
        )
        evaluation = TriggerEvaluation(
            should_trigger=True,
            trigger_probability=0.8,
            initiator_agent_id="agent_a",
            target_agent_id="agent_b",
            interaction_type="emotion_driven",
            trigger_reason="衰减测试",
        )

        with patch.object(detector, "_propagate_echo", new_callable=AsyncMock) as mock_prop:
            await detector.check_and_propagate(result, evaluation)
            echo_eval = mock_prop.call_args[0][0]
            assert echo_eval.trigger_probability == pytest.approx(0.4)

    @pytest.mark.asyncio
    async def test_echo_not_triggered_on_failure(self):
        detector = EchoDetector(echo_max_depth=3, echo_decay_ratio=0.5)
        result = InteractionResult(success=False, error="失败")
        evaluation = TriggerEvaluation(
            should_trigger=True,
            initiator_agent_id="agent_a",
            target_agent_id="agent_b",
            interaction_type="emotion_driven",
            trigger_reason="失败交互",
        )

        with patch.object(detector, "_propagate_echo", new_callable=AsyncMock) as mock_prop:
            await detector.check_and_propagate(result, evaluation)
            mock_prop.assert_not_called()


class TestMonologueTrigger:
    """6.2 内心独白触发条件验证。"""

    def test_should_trigger_high_emotion_and_idle(self):
        trigger = MonologueTrigger(
            idle_threshold_minutes=30,
            emotion_intensity_threshold=40,
            min_interval_minutes=15,
        )
        emotion_state = MagicMock()
        emotion_state.get_dominant_intensity = MagicMock(return_value=70)
        emotion_state.dominant_emotion = "lonely"
        emotion_state.emotions = {"lonely": 70, "happy": 10, "calm": 20}

        should = trigger.should_trigger("agent_a", idle_minutes=35, emotion_state=emotion_state)
        assert should

    def test_should_not_trigger_low_emotion(self):
        trigger = MonologueTrigger(
            idle_threshold_minutes=30,
            emotion_intensity_threshold=40,
            min_interval_minutes=15,
        )
        emotion_state = MagicMock()
        emotion_state.get_dominant_intensity = MagicMock(return_value=30)
        emotion_state.dominant_emotion = "calm"
        emotion_state.emotions = {"calm": 30, "happy": 20}

        should = trigger.should_trigger("agent_a", idle_minutes=35, emotion_state=emotion_state)
        assert not should

    def test_should_not_trigger_not_idle(self):
        trigger = MonologueTrigger(
            idle_threshold_minutes=30,
            emotion_intensity_threshold=40,
            min_interval_minutes=15,
        )
        emotion_state = MagicMock()
        emotion_state.get_dominant_intensity = MagicMock(return_value=70)
        emotion_state.dominant_emotion = "lonely"
        emotion_state.emotions = {"lonely": 70, "happy": 10}

        should = trigger.should_trigger("agent_a", idle_minutes=10, emotion_state=emotion_state)
        assert not should

    def test_should_not_trigger_cooldown(self):
        trigger = MonologueTrigger(
            idle_threshold_minutes=30,
            emotion_intensity_threshold=40,
            min_interval_minutes=15,
        )
        trigger.record_monologue("agent_a")

        emotion_state = MagicMock()
        emotion_state.get_dominant_intensity = MagicMock(return_value=70)
        emotion_state.dominant_emotion = "lonely"
        emotion_state.emotions = {"lonely": 70, "happy": 10}

        should = trigger.should_trigger("agent_a", idle_minutes=35, emotion_state=emotion_state)
        assert not should