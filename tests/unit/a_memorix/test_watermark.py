"""ZG-27 测试：水位偏序校验 + 状态机滞回（测试组 1——接缝测试）。"""

import pytest

from src.A_memorix.core.runtime.watermark import (
    WatermarkConfig,
    WatermarkState,
    WatermarkZone,
)


def test_watermark_config_partial_order():
    """水位偏序校验：min<=low<=high 否则 ValueError。"""
    with pytest.raises(ValueError):
        WatermarkConfig(min=10, low=5, high=20)
    with pytest.raises(ValueError):
        WatermarkConfig(min=10, low=20, high=15)
    WatermarkConfig(min=100, low=200, high=400)
    WatermarkConfig(min=100, low=100, high=100)


def test_watermark_zone_state_hysteresis():
    """水位状态机滞回判定。"""
    config = WatermarkConfig(min=100, low=200, high=400)
    zone = WatermarkZone(config=config, usage_provider=lambda: 150)
    assert zone.state() == WatermarkState.BELOW_LOW

    zone = WatermarkZone(config=config, usage_provider=lambda: 200)
    assert zone.state() == WatermarkState.BETWEEN

    zone = WatermarkZone(config=config, usage_provider=lambda: 300)
    assert zone.state() == WatermarkState.BETWEEN

    zone = WatermarkZone(config=config, usage_provider=lambda: 400)
    assert zone.state() == WatermarkState.ABOVE_HIGH

    zone = WatermarkZone(config=config, usage_provider=lambda: 500)
    assert zone.state() == WatermarkState.ABOVE_HIGH