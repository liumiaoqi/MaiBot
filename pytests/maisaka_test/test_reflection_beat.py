"""T5: M5 ReflectionBeat 测试。"""

import pytest

from src.maisaka.agent_autonomy.personality_drift.reflection_beat import ReflectionBeat


class TestTriggerConditions:
    def test_topic_changed_triggers(self):
        rb = ReflectionBeat()
        assert rb.should_trigger({"topic_changed": True}) is True

    def test_relation_level_up_triggers(self):
        rb = ReflectionBeat()
        assert rb.should_trigger({"relation_level_up": True}) is True

    def test_silence_broken_triggers(self):
        rb = ReflectionBeat()
        assert rb.should_trigger({"silence_broken": True}) is True

    def test_no_trigger_conditions(self):
        rb = ReflectionBeat()
        assert rb.should_trigger({}) is False

    def test_round_throttle_does_not_trigger(self):
        rb = ReflectionBeat()
        assert rb.should_trigger({"round_count": 5}) is False
        assert rb.should_trigger({"round_count": 10}) is False


class TestFiveQuestions:
    def test_reflect_returns_5_questions(self):
        rb = ReflectionBeat()
        result = rb.reflect("agent1", "user1", {"topic_changed": True})
        assert "q1_situation_match" in result
        assert "q2_relation_state" in result
        assert "q3_emotion_tone" in result
        assert "q4_topic_continuation" in result
        assert "q5_unique_expression" in result
        assert "weight_adjustment_suggestion" in result

    def test_reflect_values_in_range(self):
        rb = ReflectionBeat()
        result = rb.reflect("agent1", "user1", {})
        for key in ["q1_situation_match", "q3_emotion_tone", "q4_topic_continuation", "q5_unique_expression"]:
            assert 0.0 <= result[key] <= 1.0


class TestWeightSuggestion:
    def test_suggestion_contains_w_uniqueness(self):
        rb = ReflectionBeat()
        result = rb.reflect("agent1", "user1", {})
        suggestion = result["weight_adjustment_suggestion"]
        assert "w_uniqueness" in suggestion

    def test_suggestion_default_w3(self):
        rb = ReflectionBeat()
        result = rb.reflect("agent1", "user1", {})
        assert result["weight_adjustment_suggestion"]["w_uniqueness"] == pytest.approx(0.3)