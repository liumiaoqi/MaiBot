"""ZG-27 水位分级状态机（对标 Linux mm/vmscan.c watermark 体系）。

Linux 源码参考：
- include/linux/mmzone.h:797 — enum zone_watermarks WMARK_MIN/LOW/HIGH
- mm/vmscan.c:7399 — kswapd 主循环
- mm/vmscan.c:7431-7462 — kswapd_try_sleep 唤醒/休眠判定

WatermarkConfig 复制偏序校验逻辑（非 import src.core.resource_limit，AGENTS.md 核心隔离约束）。
"""

from dataclasses import dataclass
from enum import IntEnum
from typing import Callable


class WatermarkLevel(IntEnum):
    """水位三级枚举（对标 Linux include/linux/mmzone.h:797 WMARK_MIN/LOW/HIGH）。"""

    MIN = 0
    LOW = 1
    HIGH = 2


class WatermarkState(IntEnum):
    """水位状态机滞回状态。"""

    BELOW_LOW = 0
    """usage < low，需唤醒 kswapd 回收"""
    BETWEEN = 1
    """low <= usage < high，回收中"""
    ABOVE_HIGH = 2
    """usage >= high，可休眠"""


@dataclass
class WatermarkConfig:
    """水位配置（复制 ZG-5 FourTierLimit 偏序校验逻辑，非 import）。

    对标 Linux mmzone.h:797 WMARK_MIN/LOW/HIGH。
    """

    min: int
    """水位 MIN 阈值——硬底线"""
    low: int
    """水位 LOW 阈值——唤醒 kswapd"""
    high: int
    """水位 HIGH 阈值——回收目标"""
    check_interval_sec: float = 10.0
    """kswapd 检查间隔（秒）"""

    def __post_init__(self) -> None:
        if not (self.min <= self.low <= self.high):
            raise ValueError(
                f"水位偏序校验失败: min({self.min}) <= low({self.low}) <= high({self.high}) 不成立"
            )


class WatermarkZone:
    """水位状态机（对标 Linux zone_watermark_ok 滞回判定）。

    usage_provider 通过依赖注入接收（留接缝口，spec 7.4 规则 1）。
    水位检查延迟 < 1ms（纯内存读 usage_provider()，spec 4.1 规则 1）。
    """

    def __init__(self, config: WatermarkConfig, usage_provider: Callable[[], int]) -> None:
        self._config = config
        self._usage_provider = usage_provider

    def state(self) -> WatermarkState:
        """根据 usage_provider() 返回值与 config.min/low/high 比较返回滞回状态。

        对标 vmscan.c:7431-7462 kswapd_try_sleep 判定逻辑。
        """
        usage = self._usage_provider()
        if usage < self._config.low:
            return WatermarkState.BELOW_LOW
        if usage >= self._config.high:
            return WatermarkState.ABOVE_HIGH
        return WatermarkState.BETWEEN