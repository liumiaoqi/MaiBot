"""错误升级梯 — 错误计数器（ZG-14）。

每级独立计数 + 窗口归零 + 阈值升级判定。对标 Linux warn_count +
warn_limit：计数达阈触发升级，窗口结束归零（spec §5.2.1 规则 3/8）。

线程安全（spec §4.1 规则 2）：asyncio 单线程无锁快速路径（默认），
跨线程兜底时构造参数 thread_safe=True 启用 threading.Lock。
窗口计时器惰性检查（时间戳对比 + time_func 注入），不新建 timer
句柄（spec §5.2.3 异常场景 3 防泄漏）。
"""

import threading
import time
from typing import Callable

from src.core.error_escalation.config import ErrorEscalationConfig
from src.core.error_escalation.types import ErrorLevel

# 各等级的升级阈值配置项名（check_threshold 查表用）
_THRESHOLD_KEYS: dict[ErrorLevel, str] = {
    ErrorLevel.WARN: "warn_error_threshold",
    ErrorLevel.ERROR: "error_critical_threshold",
    ErrorLevel.CRITICAL: "critical_fatal_threshold",
}


class ErrorCounter:
    """每级独立计数 + 窗口归零 + 阈值升级判定。

    - check_threshold(level)：不递增，仅检查"若本次计入后是否达阈"
      （spec §5.2.1 规则 11，P0-2 修复——升级判定与递增分离）
    - increment(level)：递增计数 + 窗口惰性归零
    - bump(level)：单次调用语义（递增 + 达阈升级），兼容旧调用点
    """

    def __init__(
        self,
        config: ErrorEscalationConfig,
        *,
        time_func: Callable[[], float] = time.time,
        thread_safe: bool = False,
    ) -> None:
        """初始化计数器。

        Args:
            config: 升级配置（热更新时通过 update_config 原子替换引用）
            time_func: 时间函数注入点（测试可替换，tasks 1.9 时间注入）
            thread_safe: True 时启用 threading.Lock 跨线程兜底（默认无锁快速路径）
        """
        self._config = config
        self._time_func = time_func
        self._counts: dict[ErrorLevel, int] = {level: 0 for level in ErrorLevel}
        self._window_start: dict[ErrorLevel, float] = {}
        self._lock = threading.Lock() if thread_safe else None

    def update_config(self, config: ErrorEscalationConfig) -> None:
        """热更新配置（原子替换引用，不追溯历史计数）。"""
        self._config = config

    def check_threshold(self, level: ErrorLevel) -> ErrorLevel | None:
        """检查 level 计数是否达阈（不递增）。

        阈值=0 禁用该级计数升级（spec §5.2.1 规则 7）；判定按
        "历史计数 + 本次隐式计入"（counts[level] + 1 >= threshold），
        使"连续 N 次后第 N 次升级"成立（spec §5.2.1 规则 3 验收）。
        窗口过期先归零再判定（窗口归零是计数语义的一部分，spec
        §5.2.1 规则 8）。FATAL 无下一级，返回 None。

        Returns:
            达阈时返回下一级（ERROR/CRITICAL/FATAL），否则 None
        """
        if level is ErrorLevel.FATAL:
            return None
        if self._lock is not None:
            with self._lock:
                return self._check_threshold_unlocked(level)
        return self._check_threshold_unlocked(level)

    def _check_threshold_unlocked(self, level: ErrorLevel) -> ErrorLevel | None:
        threshold = self._get_threshold(level)
        if threshold <= 0:
            return None
        self._maybe_reset_window_unlocked(level)
        current = self._counts.get(level, 0)
        if current + 1 >= threshold:
            return _NEXT_LEVEL[level]
        return None

    def increment(self, level: ErrorLevel) -> None:
        """递增 level 计数（仅最终等级，spec §5.2.1 规则 11）。

        窗口惰性归零：count_window_sec > 0 且超窗时计数重置为 1
        并刷新窗口起点（spec §5.2.1 规则 8）。
        """
        if self._lock is not None:
            with self._lock:
                self._increment_unlocked(level)
        else:
            self._increment_unlocked(level)

    def bump(self, level: ErrorLevel) -> ErrorLevel | None:
        """单次调用语义：递增 + 达阈升级（兼容接口）。

        Returns:
            达阈时返回下一级（本次计入），否则 None
        """
        if self._lock is not None:
            with self._lock:
                return self._bump_unlocked(level)
        return self._bump_unlocked(level)

    def get_count(self, level: ErrorLevel) -> int:
        """查询指定等级当前计数。"""
        if self._lock is not None:
            with self._lock:
                return self._counts.get(level, 0)
        return self._counts.get(level, 0)

    def get_all_counts(self) -> dict[ErrorLevel, int]:
        """查询全部等级计数（副本）。"""
        if self._lock is not None:
            with self._lock:
                return dict(self._counts)
        return dict(self._counts)

    def reset_window(self, level: ErrorLevel) -> None:
        """手动清零指定等级计数与窗口起点（测试/运维用）。"""
        if self._lock is not None:
            with self._lock:
                self._reset_window_unlocked(level)
        else:
            self._reset_window_unlocked(level)

    # ── 内部（调用方持锁或单线程）──────────────────────────

    def _increment_unlocked(self, level: ErrorLevel) -> None:
        self._maybe_reset_window_unlocked(level)
        self._counts[level] = self._counts.get(level, 0) + 1

    def _bump_unlocked(self, level: ErrorLevel) -> ErrorLevel | None:
        if level is ErrorLevel.FATAL:
            self._increment_unlocked(level)
            return None
        threshold = self._get_threshold(level)
        current = self._counts.get(level, 0)
        self._increment_unlocked(level)
        if threshold > 0 and current + 1 >= threshold:
            return _NEXT_LEVEL[level]
        return None

    def _maybe_reset_window_unlocked(self, level: ErrorLevel) -> None:
        """窗口惰性归零：超窗则计数清零并刷新窗口起点。"""
        window_sec = self._config.count_window_sec
        if window_sec <= 0:
            return
        now = self._time_func()
        start = self._window_start.get(level)
        if start is not None and now - start >= window_sec:
            self._counts[level] = 0
        self._window_start[level] = now

    def _reset_window_unlocked(self, level: ErrorLevel) -> None:
        self._counts[level] = 0
        self._window_start.pop(level, None)

    def _get_threshold(self, level: ErrorLevel) -> int:
        key = _THRESHOLD_KEYS[level]
        if key == "warn_error_threshold":
            return self._config.warn_error_threshold
        if key == "error_critical_threshold":
            return self._config.error_critical_threshold
        return self._config.critical_fatal_threshold


# 各级升入的下一级（WARN→ERROR→CRITICAL→FATAL）
_NEXT_LEVEL: dict[ErrorLevel, ErrorLevel] = {
    ErrorLevel.WARN: ErrorLevel.ERROR,
    ErrorLevel.ERROR: ErrorLevel.CRITICAL,
    ErrorLevel.CRITICAL: ErrorLevel.FATAL,
}
