"""ResourceLimitConfig — 四档限制配置引擎，对标 Linux memory.min/low/high/max。

管理每插件每维度的四档阈值（min/low/high/max）+ oom_group 标志，提供四档判定。
对标 cgroup v2 的 memory.min/low/high/max 四档表达力。
"""


import time
from dataclasses import dataclass
from typing import Optional

from src.common.logger import get_logger
from src.core.resource_limit.types import (
    LimitAction,
    LimitDecision,
    LimitTier,
    ResourceDimension,
)

logger = get_logger(__name__)


@dataclass(frozen=True)
class FourTierLimit:
    """单维度四档阈值，对应 design §3.2.2。

    对标 Linux memory.min/low/high/max：
    - min_val: 硬保护量（OOM 时跳过 usage < min 的插件）
    - low_val: 软保护偏好量（超出标记 reclaimable）
    - high_val: 警戒软限（超出触发异步回收）
    - max_val: 硬限上限（超出阻断充值并触发 OOM）
    """

    min_val: int = 0
    low_val: int = 0
    high_val: int = 0
    max_val: int = 0

    def __post_init__(self) -> None:
        if not (self.min_val <= self.low_val <= self.high_val <= self.max_val):
            raise ValueError(
                f"四档偏序违反: min({self.min_val}) <= low({self.low_val}) "
                f"<= high({self.high_val}) <= max({self.max_val})"
            )

    def check_partial_order(self) -> bool:
        """校验偏序。"""
        return self.min_val <= self.low_val <= self.high_val <= self.max_val


class ResourceLimitConfig:
    """单插件资源配置，对应 design §3.2.2。"""

    def __init__(
        self,
        plugin_id: str,
        limits: Optional[dict[ResourceDimension, FourTierLimit]] = None,
        oom_group: bool = False,
        events_local: bool = False,
    ):
        self.plugin_id = plugin_id
        self.limits: dict[ResourceDimension, FourTierLimit] = limits or {}
        self.oom_group = oom_group
        self.events_local = events_local

    def get_max(self, dimension: ResourceDimension) -> Optional[int]:
        """获取某维度的 max 硬限。"""
        limit = self.limits.get(dimension)
        if limit is None:
            return None
        if limit.max_val <= 0:
            return None
        return limit.max_val

    def get_min(self, dimension: ResourceDimension) -> int:
        """获取某维度的 min 硬保护量。"""
        limit = self.limits.get(dimension)
        if limit is None:
            return 0
        return limit.min_val

    def judge(self, dimension: ResourceDimension, usage: int) -> LimitDecision:
        """四档判定，对应 design §3.2.3。

        判定五档：PROTECTED / MIN_EXCEEDED / LOW_EXCEEDED / HIGH_EXCEEDED / MAX_EXCEEDED
        未配置维度返回 UNCONFIGURED（渐进启用）。
        """
        limit = self.limits.get(dimension)
        if limit is None:
            return LimitDecision(action=LimitAction.PERMIT, tier=LimitTier.UNCONFIGURED)

        # 超 max → DENY + trigger_oom
        if limit.max_val > 0 and usage > limit.max_val:
            return LimitDecision(
                action=LimitAction.DENY,
                tier=LimitTier.MAX_EXCEEDED,
                trigger_oom=True,
            )

        # 超 high 未超 max → PERMIT + async_reclaim
        if usage > limit.high_val:
            return LimitDecision(
                action=LimitAction.PERMIT,
                tier=LimitTier.HIGH_EXCEEDED,
                async_reclaim=True,
            )

        # 超 low 未超 high → PERMIT + reclaimable
        if usage > limit.low_val:
            return LimitDecision(
                action=LimitAction.PERMIT,
                tier=LimitTier.LOW_EXCEEDED,
                reclaimable=True,
            )

        # 超 min 未超 low
        if usage > limit.min_val:
            return LimitDecision(
                action=LimitAction.PERMIT,
                tier=LimitTier.MIN_EXCEEDED,
            )

        # 未超 min → PROTECTED
        return LimitDecision(action=LimitAction.PERMIT, tier=LimitTier.PROTECTED)


class ResourceLimitConfigManager:
    """多插件配置管理 + 热更新，对应 design §3.2 + spec §4.2 可靠性 5。"""

    def __init__(self):
        self._configs: dict[str, ResourceLimitConfig] = {}
        self._last_reload_time: float = time.monotonic()

    def load_config(self, plugin_id: str, config: ResourceLimitConfig) -> bool:
        """加载单插件配置，偏序校验失败时保持上一有效配置。

        Returns:
            True 加载成功，False 偏序违反已拒绝
        """
        # FourTierLimit 在 __post_init__ 时已校验偏序，到这里说明合法
        self._configs[plugin_id] = config
        logger.debug("加载插件 %s 资源配置", plugin_id)
        return True

    def reload_config(self, configs: dict[str, ResourceLimitConfig]) -> None:
        """热更新全部配置，≤5s 生效。

        逐插件校验，违反者保持上一配置。
        """
        for plugin_id, config in configs.items():
            self.load_config(plugin_id, config)
        self._last_reload_time = time.monotonic()
        logger.info("资源配置热更新完成，共 %d 个插件", len(configs))

    def get_config(self, plugin_id: str) -> Optional[ResourceLimitConfig]:
        """获取插件配置。"""
        return self._configs.get(plugin_id)

    def get_max(self, plugin_id: str, dimension: ResourceDimension) -> Optional[int]:
        """获取插件某维度的 max 硬限（供 ResourceCounter 使用）。"""
        config = self._configs.get(plugin_id)
        if config is None:
            return None
        return config.get_max(dimension)

    def get_min(self, plugin_id: str, dimension: ResourceDimension) -> int:
        """获取插件某维度的 min 硬保护量（供 OOMHandler 使用）。"""
        config = self._configs.get(plugin_id)
        if config is None:
            return 0
        return config.get_min(dimension)

    def judge(
        self, plugin_id: str, dimension: ResourceDimension, usage: int
    ) -> LimitDecision:
        """四档判定。"""
        config = self._configs.get(plugin_id)
        if config is None:
            return LimitDecision(action=LimitAction.PERMIT, tier=LimitTier.UNCONFIGURED)
        return config.judge(dimension, usage)

    def is_oom_group(self, plugin_id: str) -> bool:
        """查询插件是否为 oom_group。"""
        config = self._configs.get(plugin_id)
        if config is None:
            return False
        return config.oom_group

    def is_events_local(self, plugin_id: str) -> bool:
        """查询插件事件是否仅本地。"""
        config = self._configs.get(plugin_id)
        if config is None:
            return False
        return config.events_local