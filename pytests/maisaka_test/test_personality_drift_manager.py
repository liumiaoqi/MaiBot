"""T3: M3 PersonalityDriftManager 测试。"""

from unittest.mock import MagicMock

import pytest

from src.maisaka.agent.config import LayeredPersonality, PersonalityLayer
from src.maisaka.agent_autonomy.personality_drift.drift_params import DriftParams
from src.maisaka.agent_autonomy.personality_drift.personality_drift_manager import (
    PersonalityDriftManager,
)


def _make_manager(enabled: bool = True, drift_period: int = 500) -> PersonalityDriftManager:
    config = {
        "enabled": enabled,
        "drift_period": drift_period,
        "regression_rate": 0.03,
        "sigma_max": 0.3,
        "selection_ratio": 2 / 12,
    }
    persistence = MagicMock()
    plasticity = MagicMock()
    plasticity.compute.return_value = 0.5
    fitness = MagicMock()
    fitness.collect.return_value = 0.5
    return PersonalityDriftManager(config, persistence, plasticity, fitness)


class TestDriftDisabled:
    def test_disabled_noop(self):
        manager = _make_manager(enabled=False)
        lp = LayeredPersonality()
        original = lp.get_layer_text(PersonalityLayer.EXPRESSION)
        manager.on_tick("agent1", 500, lp, "user1")
        assert lp.get_layer_text(PersonalityLayer.EXPRESSION) == original

    def test_not_at_period_noop(self):
        manager = _make_manager(enabled=True, drift_period=500)
        lp = LayeredPersonality()
        original = lp.get_layer_text(PersonalityLayer.EXPRESSION)
        manager.on_tick("agent1", 499, lp, "user1")
        assert lp.get_layer_text(PersonalityLayer.EXPRESSION) == original

    def test_zero_count_noop(self):
        manager = _make_manager(enabled=True, drift_period=500)
        lp = LayeredPersonality()
        original = lp.get_layer_text(PersonalityLayer.EXPRESSION)
        manager.on_tick("agent1", 0, lp, "user1")
        assert lp.get_layer_text(PersonalityLayer.EXPRESSION) == original


class TestDriftStep:
    def test_drift_changes_params(self):
        manager = _make_manager(enabled=True, drift_period=500)
        lp = LayeredPersonality()
        lp.set_layer_text(PersonalityLayer.EXPRESSION, DriftParams().to_layer_text())
        original = DriftParams.from_layer_text(lp.get_layer_text(PersonalityLayer.EXPRESSION))
        manager.on_tick("agent1", 500, lp, "user1")
        after = DriftParams.from_layer_text(lp.get_layer_text(PersonalityLayer.EXPRESSION))
        changed = any(
            abs(o.value - a.value) > 1e-9
            for o, a in zip(original.all_params(), after.all_params(), strict=True)
        )
        assert changed

    def test_drift_params_within_bounds(self):
        manager = _make_manager(enabled=True, drift_period=100)
        lp = LayeredPersonality()
        lp.set_layer_text(PersonalityLayer.EXPRESSION, DriftParams().to_layer_text())
        for i in range(100, 1000, 100):
            manager.on_tick("agent1", i, lp, "user1")
        params = DriftParams.from_layer_text(lp.get_layer_text(PersonalityLayer.EXPRESSION))
        for p in params.all_params():
            assert p.min_val <= p.value <= p.max_val


class TestRegression:
    def test_regression_pulls_to_initial(self):
        manager = _make_manager(enabled=True, drift_period=500)
        params = DriftParams()
        params.exploration_rate.value = 1.0
        params.exploration_rate.initial_value = 0.5
        manager._regression(params)
        expected = 1.0 * 0.97 + 0.5 * 0.03
        assert params.exploration_rate.value == pytest.approx(expected, abs=0.01)


class TestEvolutionCage:
    def test_multiple_drifts_within_bounds(self):
        manager = _make_manager(enabled=True, drift_period=10)
        lp = LayeredPersonality()
        lp.set_layer_text(PersonalityLayer.EXPRESSION, DriftParams().to_layer_text())
        for i in range(10, 3010, 10):
            manager.on_tick("agent1", i, lp, "user1")
        params = DriftParams.from_layer_text(lp.get_layer_text(PersonalityLayer.EXPRESSION))
        for p in params.all_params():
            assert p.min_val <= p.value <= p.max_val