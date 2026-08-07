"""降级日志抑制（ZG-2 SUP 域）+ 健康等级接入点（STT 域）。

四级策略表（health_suppression_map）+ 豁免组件 + 防抖；
set_health_level_provider 单一来源语义，无 provider/异常回退 HEALTHY。
本模块不依赖 src/core/ 具体类（CMP-05）——SystemHealthLevel 以字符串弱引用。
"""

import logging
import threading
import time
from typing import Callable

# 健康等级字符串（与 src/core/service_manager/types.py 的 SystemHealthLevel 值一致）
_HEALTH_LEVELS = {"healthy", "degraded", "fault", "recovering"}

_LEVELNO = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
    "none": 0,
}

_health_level_provider: Callable[[], object | None] | None = None
_provider_lock = threading.Lock()


def set_health_level_provider(provider: Callable[[], object | None]) -> None:
    """注入健康等级来源（ZG-6 落地后接线）。单一来源：后注册覆盖。"""
    global _health_level_provider
    with _provider_lock:
        _health_level_provider = provider


def _get_current_health_level() -> str:
    """返回当前等级：无 provider / 调用异常 → HEALTHY（异常隔离，STT-02-2）。"""
    global _health_level_provider
    with _provider_lock:
        provider = _health_level_provider
    if provider is None:
        return "healthy"
    try:
        level = provider()
        if level is None:
            return "healthy"
        value = getattr(level, "value", level)
        if value in _HEALTH_LEVELS:
            return value
        return "healthy"
    except Exception as exc:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.WARNING, "读取当前健康等级失败，返回 healthy", exception=exc)
        return "healthy"


class Suppressor:
    """降级日志抑制器：健康等级 → 抑制线映射 + 豁免组件 + 防抖。"""

    def __init__(
        self,
        health_map: dict[str, str],
        exempt_components: tuple[str, ...],
        debounce_s: float,
    ) -> None:
        self._health_map = {k: _LEVELNO.get(v, 0) for k, v in health_map.items()}
        self._exempt = exempt_components
        self._debounce_s = debounce_s
        self._current_level = "healthy"
        self._last_switch = 0.0
        self._lock = threading.Lock()

    def set_health_level(self, level: str | None) -> None:
        """设置当前健康等级；None 表示来源不可用（回退 HEALTHY）。防抖在此实现。"""
        new_level = level if level in _HEALTH_LEVELS else "healthy"
        with self._lock:
            now = time.monotonic()
            if new_level != self._current_level:
                if now - self._last_switch < self._debounce_s:
                    return  # 防抖：切换间隔不足则保持
                self._current_level = new_level
            self._last_switch = now  # 每次调用都刷新（防抖覆盖首次切换后的窗口）

    def current_threshold(self) -> int:
        """返回当前抑制线（日志 levelno 低于此值则抑制）。"""
        with self._lock:
            return self._health_map.get(self._current_level, 0)

    def should_suppress(self, levelno: int, logger_name: str) -> bool:
        """True 表示应抑制（低于抑制线且不在豁免组件）。"""
        with self._lock:
            threshold = self._health_map.get(self._current_level, 0)
        if threshold == 0:
            return False
        if levelno >= threshold:
            return False
        # 豁免组件（logger_name 前缀匹配）
        for prefix in self._exempt:
            if logger_name.startswith(prefix):
                return False
        return True

    def current_line(self) -> str:
        """内省：当前生效抑制线。"""
        threshold = self.current_threshold()
        for name, no in _LEVELNO.items():
            if no == threshold:
                return name
        return "none"
