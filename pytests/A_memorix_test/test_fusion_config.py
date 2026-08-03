"""MF-M-002 验收：FusionConfig（R03+R04：仅 stage，无 enabled）。

对应 tasks.md 8.1：stage 默认 FUSION_OFF；各属性读取正确；无效 stage 回退。
"""

from src.A_memorix.core.concept_graph.fusion_config import FusionConfig


def test_stage_default_off() -> None:
    assert FusionConfig().stage == "fusion_off"


def test_stage_read_from_config() -> None:
    assert FusionConfig({"stage": "FUSION_FULL"}).stage == "fusion_full"
    assert FusionConfig({"stage": "fusion_write"}).stage == "fusion_write"


def test_invalid_stage_falls_back_to_off() -> None:
    assert FusionConfig({"stage": "bogus"}).stage == "fusion_off"


def test_no_enabled_attribute() -> None:
    """R03+R04：仅 stage 属性，无 enabled。"""
    config = FusionConfig()
    assert not hasattr(config, "enabled")
    assert config.stage == "fusion_off"


def test_spread_depth_default_and_config() -> None:
    assert FusionConfig().spread_depth == 3
    assert FusionConfig({"spread_depth": 5}).spread_depth == 5
    assert FusionConfig({"spread_depth": 0}).spread_depth == 3  # 0 → 回退默认
    assert FusionConfig({"spread_depth": -2}).spread_depth == 1  # 下限保护


def test_score_alpha_default_and_clamp() -> None:
    assert FusionConfig().score_alpha == 0.5
    assert FusionConfig({"score_alpha": 0.3}).score_alpha == 0.3
    assert FusionConfig({"score_alpha": 2.0}).score_alpha == 1.0


def test_write_lock_timeout_default_and_config() -> None:
    assert FusionConfig().write_lock_timeout == 5.0
    assert FusionConfig({"write_lock_timeout": 3.0}).write_lock_timeout == 3.0


def test_stage_predicates() -> None:
    assert FusionConfig({"stage": "fusion_full"}).is_full() is True
    assert FusionConfig({"stage": "fusion_write"}).is_write_enabled() is True
    assert FusionConfig({"stage": "fusion_full"}).is_write_enabled() is True
    assert FusionConfig().is_full() is False
    assert FusionConfig().is_write_enabled() is False
