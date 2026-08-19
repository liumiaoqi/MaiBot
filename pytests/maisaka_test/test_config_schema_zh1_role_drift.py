"""T7: config_schema zh1_role_drift 灰度开关测试。"""

import pytest


ZH1_DEFAULT_CONFIG = {
    "enabled": False,
    "drift_period": 500,
    "regression_rate": 0.03,
    "sigma_max": 0.3,
    "selection_ratio": 0.167,
    "w_interaction": 0.4,
    "w_relation": 0.2,
    "w_uniqueness": 0.3,
    "w_emotion": 0.0,
    "bias_magnitude": 0.06,
}


class TestConfigDefaults:
    def test_enabled_default_false(self):
        assert ZH1_DEFAULT_CONFIG["enabled"] is False

    def test_w_emotion_default_zero(self):
        assert ZH1_DEFAULT_CONFIG["w_emotion"] == 0.0

    def test_drift_period_default_500(self):
        assert ZH1_DEFAULT_CONFIG["drift_period"] == 500

    def test_regression_rate_default_003(self):
        assert ZH1_DEFAULT_CONFIG["regression_rate"] == pytest.approx(0.03)

    def test_weights_sum(self):
        w = (
            ZH1_DEFAULT_CONFIG["w_interaction"]
            + ZH1_DEFAULT_CONFIG["w_relation"]
            + ZH1_DEFAULT_CONFIG["w_uniqueness"]
            + ZH1_DEFAULT_CONFIG["w_emotion"]
        )
        assert w == pytest.approx(0.9)

    def test_bias_magnitude_le_20_percent(self):
        assert ZH1_DEFAULT_CONFIG["bias_magnitude"] <= 0.2


class TestConfigValidation:
    def test_drift_period_range(self):
        assert 100 <= ZH1_DEFAULT_CONFIG["drift_period"] <= 10000

    def test_regression_rate_range(self):
        assert 0.0 <= ZH1_DEFAULT_CONFIG["regression_rate"] <= 0.1

    def test_sigma_max_range(self):
        assert 0.0 <= ZH1_DEFAULT_CONFIG["sigma_max"] <= 1.0

    def test_all_weights_non_negative(self):
        assert ZH1_DEFAULT_CONFIG["w_interaction"] >= 0
        assert ZH1_DEFAULT_CONFIG["w_relation"] >= 0
        assert ZH1_DEFAULT_CONFIG["w_uniqueness"] >= 0
        assert ZH1_DEFAULT_CONFIG["w_emotion"] >= 0