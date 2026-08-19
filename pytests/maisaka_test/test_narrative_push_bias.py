"""T4: M4 NarrativePushBias 测试。"""

import pytest

from src.maisaka.agent_autonomy.personality_drift.drift_params import DriftParams
from src.maisaka.agent_autonomy.personality_drift.narrative_push_bias import (

    NarrativePushBias,
)


class TestEventMapping:
    def test_join_group_increases_social_and_exploration(self):
        bias = NarrativePushBias()
        params = DriftParams()
        orig_social = params.social_strength.value
        orig_explore = params.exploration_rate.value
        bias.on_event("join_group", params)
        assert params.social_strength.value > orig_social
        assert params.exploration_rate.value > orig_explore

    def test_leave_group_decreases_social(self):
        bias = NarrativePushBias()
        params = DriftParams()
        orig = params.social_strength.value
        bias.on_event("leave_group", params)
        assert params.social_strength.value < orig

    def test_long_silence_decreases_vitality(self):
        bias = NarrativePushBias()
        params = DriftParams()
        orig = params.vitality_intensity.value
        bias.on_event("long_silence", params)
        assert params.vitality_intensity.value < orig

    def test_unknown_event_noop(self):
        bias = NarrativePushBias()
        params = DriftParams()
        orig = params.exploration_rate.value
        bias.on_event("unknown_event", params)
        assert params.exploration_rate.value == pytest.approx(orig)


class TestBiasMagnitude:
    def test_magnitude_le_6_percent(self):
        bias = NarrativePushBias()
        params = DriftParams()
        orig = params.social_strength.value
        bias.on_event("join_group", params)
        delta = abs(params.social_strength.value - orig)
        assert delta <= 0.06 + 1e-9

    def test_custom_magnitude(self):
        bias = NarrativePushBias({"bias_magnitude": 0.1})
        params = DriftParams()
        orig = params.social_strength.value
        bias.on_event("join_group", params)
        delta = abs(params.social_strength.value - orig)
        assert delta == pytest.approx(0.1)


class TestBiasTemporary:
    def test_bias_clamped(self):
        bias = NarrativePushBias({"bias_magnitude": 0.5})
        params = DriftParams()
        bias.on_event("join_group", params)
        assert params.social_strength.value <= params.social_strength.max_val

    def test_clear_bias_noop(self):
        bias = NarrativePushBias()
        params = DriftParams()
        bias.clear_bias(params)