"""Per-Plugin 速率限制 — 滑动窗口实现。

使用 collections.deque 存储时间戳，asyncio 单线程无需加锁。
"""


import time
from collections import deque

from src.common.logger import get_logger

logger = get_logger("plugin_runtime_v2.host.rate_limiter")


class PluginRateLimiter:
    """Per-plugin RPM 速率限制器。"""

    def __init__(self, default_rpm: int = 60) -> None:
        self._default_rpm = max(1, default_rpm)
        self._limits: dict[str, int] = {}
        self._windows: dict[str, deque[float]] = {}

    def check(self, plugin_id: str) -> bool:
        """滑动窗口检查。True=允许，False=超限。"""
        rpm = self._limits.get(plugin_id, self._default_rpm)
        now = time.time()
        window = self._windows.setdefault(plugin_id, deque())

        # 清理过期时间戳（超过 60 秒的）
        while window and now - window[0] > 60.0:
            window.popleft()

        if len(window) >= rpm:
            logger.debug("plugin %s 速率限制触发: %d/%d rpm", plugin_id, len(window), rpm)
            return False

        window.append(now)
        return True

    def set_limit(self, plugin_id: str, rpm: int) -> None:
        """设置自定义限制。"""
        self._limits[plugin_id] = max(1, rpm)

    def reset(self, plugin_id: str) -> None:
        """重置指定插件的计数器。"""
        self._windows.pop(plugin_id, None)
        self._limits.pop(plugin_id, None)
