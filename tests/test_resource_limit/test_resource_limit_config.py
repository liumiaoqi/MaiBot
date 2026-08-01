"""ResourceLimitConfig 单元测试 — 对应 tasks §3.3。"""


import pytest

from src.core.resource_limit.resource_limit_config import (
    FourTierLimit,
    ResourceLimitConfig,
    ResourceLimitConfigManager,
)
from src.core.resource_limit.types import LimitAction, LimitTier, ResourceDimension


class TestFourTierLimit:
    """四档阈值偏序校验。"""

    def test_partial_order_valid(self):
        """合法偏序加载成功。"""
        fl = FourTierLimit(10, 50, 100, 200)
        assert fl.check_partial_order() is True

    def test_partial_order_violation(self):
        """min > low 拒绝。"""
        with pytest.raises(ValueError):
            FourTierLimit(100, 50, 100, 200)

    def test_partial_order_violation_high_max(self):
        """high > max 拒绝。"""
        with pytest.raises(ValueError):
            FourTierLimit(0, 0, 200, 100)


class TestResourceLimitConfig:
    """四档判定算法。"""

    @pytest.fixture
    def config(self):
        fl = FourTierLimit(10, 50, 100, 200)
        return ResourceLimitConfig("a", {ResourceDimension.TOKEN: fl})

    def test_judge_protected(self, config):
        """usage < min → PROTECTED。"""
        result = config.judge(ResourceDimension.TOKEN, 5)
        assert result.tier == LimitTier.PROTECTED

    def test_judge_min_exceeded(self, config):
        """min < usage < low → MIN_EXCEEDED。"""
        result = config.judge(ResourceDimension.TOKEN, 20)
        assert result.tier == LimitTier.MIN_EXCEEDED

    def test_judge_low_exceeded(self, config):
        """low < usage < high → LOW_EXCEEDED (reclaimable)。"""
        result = config.judge(ResourceDimension.TOKEN, 60)
        assert result.tier == LimitTier.LOW_EXCEEDED
        assert result.reclaimable is True

    def test_judge_high_exceeded(self, config):
        """high < usage < max → HIGH_EXCEEDED (async_reclaim)。"""
        result = config.judge(ResourceDimension.TOKEN, 120)
        assert result.tier == LimitTier.HIGH_EXCEEDED
        assert result.async_reclaim is True

    def test_judge_max_exceeded(self, config):
        """usage > max → MAX_EXCEEDED (trigger_oom)。"""
        result = config.judge(ResourceDimension.TOKEN, 250)
        assert result.tier == LimitTier.MAX_EXCEEDED
        assert result.trigger_oom is True
        assert result.action == LimitAction.DENY

    def test_unconfigured_dimension(self, config):
        """未配置维度不限流。"""
        result = config.judge(ResourceDimension.MEMORY, 999999)
        assert result.tier == LimitTier.UNCONFIGURED
        assert result.action == LimitAction.PERMIT


class TestResourceLimitConfigManager:
    """多插件配置管理。"""

    def test_load_and_get(self):
        """加载配置并查询。"""
        mgr = ResourceLimitConfigManager()
        fl = FourTierLimit(10, 50, 100, 200)
        cfg = ResourceLimitConfig("a", {ResourceDimension.TOKEN: fl})
        assert mgr.load_config("a", cfg) is True
        assert mgr.get_max("a", ResourceDimension.TOKEN) == 200
        assert mgr.get_min("a", ResourceDimension.TOKEN) == 10

    def test_unconfigured_plugin(self):
        """未配置插件返回 None。"""
        mgr = ResourceLimitConfigManager()
        assert mgr.get_max("nonexistent", ResourceDimension.TOKEN) is None
        assert mgr.get_min("nonexistent", ResourceDimension.TOKEN) == 0

    def test_judge_unconfigured(self):
        """未配置插件判定为 UNCONFIGURED。"""
        mgr = ResourceLimitConfigManager()
        result = mgr.judge("nonexistent", ResourceDimension.TOKEN, 100)
        assert result.tier == LimitTier.UNCONFIGURED

    def test_oom_group(self):
        """oom_group 标志查询。"""
        mgr = ResourceLimitConfigManager()
        cfg = ResourceLimitConfig("a", oom_group=True)
        mgr.load_config("a", cfg)
        assert mgr.is_oom_group("a") is True
        assert mgr.is_oom_group("b") is False