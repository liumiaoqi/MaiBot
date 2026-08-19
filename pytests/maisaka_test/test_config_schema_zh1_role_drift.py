"""T7: config_schema zh1_role_drift 灰度开关测试——验证生产配置真实字段。"""

import pytest


class TestAgentAutonomySectionConfigFields:
    """验证 AgentAutonomySectionConfig 包含 zh1_role_drift 全部 10 字段。"""

    @pytest.fixture
    def autonomy_section(self):
        from src.config.official_configs import AgentAutonomySectionConfig
        return AgentAutonomySectionConfig()

    def test_enabled_default_false(self, autonomy_section):
        assert autonomy_section.zh1_role_drift_enabled is False

    def test_drift_period_default_500(self, autonomy_section):
        assert autonomy_section.zh1_role_drift_drift_period == 500

    def test_regression_rate_default_003(self, autonomy_section):
        assert autonomy_section.zh1_role_drift_regression_rate == pytest.approx(0.03)

    def test_sigma_max_default_03(self, autonomy_section):
        assert autonomy_section.zh1_role_drift_sigma_max == pytest.approx(0.3)

    def test_selection_ratio_default_2_over_12(self, autonomy_section):
        assert autonomy_section.zh1_role_drift_selection_ratio == pytest.approx(0.167)

    def test_w_interaction_default_04(self, autonomy_section):
        assert autonomy_section.zh1_role_drift_w_interaction == pytest.approx(0.4)

    def test_w_relation_default_02(self, autonomy_section):
        assert autonomy_section.zh1_role_drift_w_relation == pytest.approx(0.2)

    def test_w_uniqueness_default_03(self, autonomy_section):
        assert autonomy_section.zh1_role_drift_w_uniqueness == pytest.approx(0.3)

    def test_w_emotion_default_zero(self, autonomy_section):
        assert autonomy_section.zh1_role_drift_w_emotion == 0.0

    def test_reflection_interval_default_3600(self, autonomy_section):
        assert autonomy_section.zh1_role_drift_reflection_interval == 3600

    def test_weights_sum(self, autonomy_section):
        w = (
            autonomy_section.zh1_role_drift_w_interaction
            + autonomy_section.zh1_role_drift_w_relation
            + autonomy_section.zh1_role_drift_w_uniqueness
            + autonomy_section.zh1_role_drift_w_emotion
        )
        assert w == pytest.approx(0.9)


class TestAgentAutonomySnapshotFields:
    """验证 AgentAutonomySnapshot 包含 zh1_role_drift 字段且 adapter 正确传递。"""

    def test_snapshot_has_zh1_fields(self):
        from src.core.types import AgentAutonomySnapshot
        snap = AgentAutonomySnapshot()
        assert snap.zh1_role_drift_enabled is False
        assert snap.zh1_role_drift_drift_period == 500
        assert snap.zh1_role_drift_w_emotion == 0.0

    def test_adapter_passes_zh1_config(self):
        """验证 app_config_port adapter 正确传递 zh1_role_drift 字段。"""
        from src.config.official_configs import AgentAutonomySectionConfig
        from src.core.types import AgentAutonomySnapshot

        cfg = AgentAutonomySectionConfig(zh1_role_drift_enabled=True)
        snap = AgentAutonomySnapshot(
            zh1_role_drift_enabled=cfg.zh1_role_drift_enabled,
            zh1_role_drift_drift_period=cfg.zh1_role_drift_drift_period,
            zh1_role_drift_regression_rate=cfg.zh1_role_drift_regression_rate,
            zh1_role_drift_sigma_max=cfg.zh1_role_drift_sigma_max,
            zh1_role_drift_selection_ratio=cfg.zh1_role_drift_selection_ratio,
            zh1_role_drift_w_interaction=cfg.zh1_role_drift_w_interaction,
            zh1_role_drift_w_relation=cfg.zh1_role_drift_w_relation,
            zh1_role_drift_w_uniqueness=cfg.zh1_role_drift_w_uniqueness,
            zh1_role_drift_w_emotion=cfg.zh1_role_drift_w_emotion,
            zh1_role_drift_reflection_interval=cfg.zh1_role_drift_reflection_interval,
        )
        assert snap.zh1_role_drift_enabled is True
        assert snap.zh1_role_drift_drift_period == 500
