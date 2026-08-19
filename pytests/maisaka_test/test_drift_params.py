"""T1: M1 DriftParams dataclass 测试。"""

import pytest

from src.maisaka.agent.config import LayeredPersonality, PersonalityLayer
from src.maisaka.agent_autonomy.personality_drift.drift_params import (
    DriftParam,
    DriftParams,
)


class TestDriftParamsSerialization:
    def test_roundtrip(self):
        params = DriftParams()
        text = params.to_layer_text()
        restored = DriftParams.from_layer_text(text)
        for p_orig, p_restored in zip(params.all_params(), restored.all_params(), strict=True):
            assert p_orig.name == p_restored.name
            assert p_orig.value == pytest.approx(p_restored.value)
            assert p_orig.min_val == pytest.approx(p_restored.min_val)
            assert p_orig.max_val == pytest.approx(p_restored.max_val)

    def test_from_empty_text_returns_defaults(self):
        params = DriftParams.from_layer_text("")
        assert params is not None
        assert params.exploration_rate.value == pytest.approx(0.5)

    def test_from_invalid_text_returns_defaults(self):
        params = DriftParams.from_layer_text("not json")
        assert params.exploration_rate.value == pytest.approx(0.5)


class TestDriftParamsClamp:
    def test_clamp_within_bounds(self):
        p = DriftParam("test", 0.5, 0.0, 1.0, 0.5)
        p.value = 1.5
        p.clamp()
        assert p.value == pytest.approx(1.0)

    def test_clamp_below_bounds(self):
        p = DriftParam("test", 0.5, 0.0, 1.0, 0.5)
        p.value = -0.5
        p.clamp()
        assert p.value == pytest.approx(0.0)

    def test_clamp_all(self):
        params = DriftParams()
        params.exploration_rate.value = 999.0
        params.social_polarity.value = -999.0
        params.clamp_all()
        assert params.exploration_rate.value == pytest.approx(1.0)
        assert params.social_polarity.value == pytest.approx(-1.0)


class TestExistenceImmutable:
    def test_existence_not_modifiable(self):
        lp = LayeredPersonality()
        assert lp.is_modifiable(PersonalityLayer.EXISTENCE) is False

    def test_expression_modifiable(self):
        lp = LayeredPersonality()
        assert lp.is_modifiable(PersonalityLayer.EXPRESSION) is True

    def test_set_existence_raises(self):
        lp = LayeredPersonality()
        with pytest.raises(ValueError):
            lp.set_layer_text(PersonalityLayer.EXISTENCE, "test")

    def test_set_expression_ok(self):
        lp = LayeredPersonality()
        lp.set_layer_text(PersonalityLayer.EXPRESSION, "test")
        assert lp.get_layer_text(PersonalityLayer.EXPRESSION) == "test"


class TestDriftParamsAllParams:
    def test_all_params_count(self):
        params = DriftParams()
        all_p = params.all_params()
        assert len(all_p) == 10

    def test_get_param_by_name(self):
        params = DriftParams()
        p = params.get_param("exploration_rate")
        assert p is not None
        assert p.name == "exploration_rate"

    def test_get_param_not_found(self):
        params = DriftParams()
        assert params.get_param("nonexistent") is None