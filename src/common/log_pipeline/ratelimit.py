"""日志频率抑制（ZG-2 RTL 域）。

固定计数窗口（window_s / max_events），source_key = (logger_name, event_signature)，
ERROR/CRITICAL 默认豁免（apply_levels 不含），白名单前缀逐条放行，
窗口过期输出摘要（rate_limit=true）。
"""

import logging
import threading
import time
from typing import Callable
from dataclasses import dataclass


@dataclass
class WindowState:
    """单来源窗口状态。"""

    window_start: float
    count: int = 0
    suppressed_count: int = 0
    first_ts: float = 0.0
    last_ts: float = 0.0
    event: str = ""
    logger_name: str = ""
    summary_pending: bool = False


class RateLimiter:
    """同源高频抑制（固定计数窗口）。"""

    def __init__(
        self,
        window_s: float,
        max_events: int,
        apply_levels: set[int],
        whitelist: tuple[str, ...],
        summary_interval_s: float,
    ) -> None:
        self._window_s = window_s
        self._max_events = max_events
        self._apply_levels = apply_levels
        self._whitelist = whitelist
        self._summary_interval_s = summary_interval_s
        self._windows: dict[tuple[str, str], WindowState] = {}
        self._lock = threading.RLock()
        self._total_suppressed = 0
        self._last_summary_flush = 0.0

    def check(self, record: logging.LogRecord) -> bool:
        """返回 True 放行 / False 抑制。

        同源超阈值则抑制并累计 suppressed_count；窗口过期时标记待输出摘要
        （不在本方法内同步输出，NFR-PER-03）。
        """
        with self._lock:
            # ERROR/CRITICAL 豁免（RTL-04）
            if record.levelno not in self._apply_levels:
                return True
            # 白名单逐条放行（RTL-02）
            if self._is_whitelisted(record.name):
                return True

            key = self._source_key(record)
            now = time.monotonic()
            window = self._windows.get(key)

            if window is None or now - window.window_start >= self._window_s:
                # 新窗口（旧窗口已过期 → 标记摘要）
                if window is not None:
                    window.summary_pending = True
                window = WindowState(window_start=now, first_ts=now, last_ts=now)
                window.event = self._event_text(record)
                window.logger_name = record.name
                self._windows[key] = window

            window.last_ts = now
            window.count += 1

            if window.count <= self._max_events:
                return True

            # 抑制
            window.suppressed_count += 1
            self._total_suppressed += 1
            return False

    def emit_summaries(self, output: Callable[[dict], None]) -> None:
        """窗口结束的摘要批量输出（由事件循环调度调用）。

        摘要字段：source/event/actual_count/suppressed_count/first_ts/last_ts/rate_limit=true。
        """
        with self._lock:
            now = time.monotonic()
            # 惰性清理 + 摘要输出
            expired_keys = [
                key
                for key, w in self._windows.items()
                if now - w.window_start >= self._window_s
            ]
            for key in expired_keys:
                window = self._windows.pop(key)
                if window.suppressed_count > 0:
                    output({
                        "source": key[0],
                        "event": window.event,
                        "actual_count": window.count,
                        "suppressed_count": window.suppressed_count,
                        "first_ts": window.first_ts,
                        "last_ts": window.last_ts,
                        "rate_limit": True,
                    })
            self._last_summary_flush = now

    def stats(self) -> dict:
        """内省：活跃源数、总抑制计数（MNT-02）。"""
        with self._lock:
            return {
                "active_sources": len(self._windows),
                "total_suppressed": self._total_suppressed,
            }

    # ── 内部 ──────────────────────────────────────────────

    @staticmethod
    def _source_key(record: logging.LogRecord) -> tuple[str, str]:
        """来源键：logger_name + 事件签名（消息文本截断前 80 字符）。"""
        event = (record.getMessage() or "")[:80]
        return (record.name, event)

    @staticmethod
    def _event_text(record: logging.LogRecord) -> str:
        return (record.getMessage() or "")[:120]

    def _is_whitelisted(self, logger_name: str) -> bool:
        for prefix in self._whitelist:
            if logger_name.startswith(prefix):
                return True
        return False
