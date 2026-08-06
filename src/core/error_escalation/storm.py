"""错误升级梯 — 错误风暴抑制器（ZG-14）。

单一错误源（component_id + message 指纹）高频触发检测 + ONCE 抑制 +
风暴源标记/恢复。对标 Linux printk 限速（rate-limit）与 oops 风暴
检测（oops_count 连续检测）。

抑制仅影响 LOG/NOTIFY 等高开销动作，COUNT 必须全量（spec §5.4.1
规则 5）——升级判定依赖全量计数。
"""

import time
from dataclasses import dataclass
from typing import Callable

from src.core.error_escalation.config import ErrorEscalationConfig
from src.core.error_escalation.types import ErrorLevel

# 指纹 None（未知源）聚合键（spec §5.4.3 异常场景 1）
_UNKNOWN_SOURCE = "<unknown-source>"


@dataclass(frozen=True)
class StormDecision:
    """风暴抑制决策（每次 check 生成）。

    - log_allowed: False 时 LOG 静默（ONCE 已触发或风暴源已响应）
    - force_once: True 时本次是风暴源唯一完整响应（风暴期间只此一次）
    - is_storm_source: True 时该源已被标记为风暴源
    """

    log_allowed: bool
    force_once: bool
    is_storm_source: bool


@dataclass
class _SourceWindow:
    """单一源的窗口状态（count_window_sec 内触发计数）。"""

    count: int = 0
    start: float = 0.0
    last_trigger: float = 0.0


class StormTracker:
    """错误风暴检测 + ONCE 抑制 + 风暴源标记/恢复。

    - ONCE 抑制（spec §5.4.1 规则 1）：once=True 同源仅首次完整响应，
      后续静默计数；_once_fired 进程生命周期内不重置（spec §6.5 字段 4）
    - 风暴检测（spec §5.4.1 规则 3）：窗口内触发次数 ≥
      max(该级计数阈值 × 10, storm_min_threshold) 自动标记风暴源，
      阈值=0 时 storm_min_threshold（默认 100）保证检测仍有效（P2-3）
    - 风暴恢复（spec §5.4.1 规则 4）：count_window_sec × 3 无新触发
      自动解除；count_window_sec=0（全局累计）时不自动恢复——
      全局累计模式风暴检测只升不降，需显式 clear_storm（设计决策）
    """

    def __init__(
        self,
        config: ErrorEscalationConfig,
        *,
        time_func: Callable[[], float] = time.time,
    ) -> None:
        self._config = config
        self._time_func = time_func
        self._storm_sources: set[str] = set()
        self._once_fired: set[str] = set()
        self._source_windows: dict[str, _SourceWindow] = {}

    def update_config(self, config: ErrorEscalationConfig) -> None:
        """热更新配置（原子替换引用，风暴源/ONCE 状态保留）。"""
        self._config = config

    def check(self, fingerprint: str | None, once: bool, level: ErrorLevel) -> StormDecision:
        """上报前抑制检查（每次上报调用，含窗口计数）。

        Args:
            fingerprint: 源指纹（component_id + message 哈希），None 按
                "未知源"聚合（spec §5.4.3 异常场景 1）
            once: 本次上报是否带 ONCE 标志（spec §5.4.1 规则 1）
            level: 本次上报等级（风暴检测阈值按该级计数阈值 × 10）

        Returns:
            抑制决策（log_allowed/force_once/is_storm_source）
        """
        fp = fingerprint if fingerprint is not None else _UNKNOWN_SOURCE
        now = self._time_func()
        win = self._source_windows.get(fp)

        # 窗口惰性重置（count_window_sec=0 时全局累计不重置）
        window_sec = self._config.count_window_sec
        if win is None or (window_sec > 0 and now - win.start >= window_sec):
            win = _SourceWindow(start=now)
            self._source_windows[fp] = win

        # 风暴恢复：风暴源 count_window_sec × 3 无新触发自动解除
        # （spec §5.4.1 规则 4；count_window_sec=0 时不自动恢复）
        if fp in self._storm_sources and window_sec > 0:
            if now - win.last_trigger >= window_sec * 3:
                self.clear_storm(fp)

        # 风暴检测：窗口内触发次数 ≥ max(该级阈值 × 10, storm_min_threshold)
        threshold = self._storm_threshold_for(level)
        win.count += 1
        win.last_trigger = now
        if win.count >= threshold:
            self.mark_storm(fp)

        if fp in self._storm_sources:
            # 风暴源：强制 ONCE 模式——仅允许一次完整响应（LOG/NOTIFY 抑制）
            if fp in self._once_fired:
                return StormDecision(log_allowed=False, force_once=False, is_storm_source=True)
            self._once_fired.add(fp)
            return StormDecision(log_allowed=True, force_once=True, is_storm_source=True)

        # 非风暴源：once=True 且已触发过 → 静默；否则完整响应
        if once:
            if fp in self._once_fired:
                return StormDecision(log_allowed=False, force_once=False, is_storm_source=False)
            self._once_fired.add(fp)
        return StormDecision(log_allowed=True, force_once=False, is_storm_source=False)

    def mark_storm(self, fingerprint: str | None) -> None:
        """显式标记风暴源（检测到风暴时自动调用，也可外部调用）。"""
        fp = fingerprint if fingerprint is not None else _UNKNOWN_SOURCE
        self._storm_sources.add(fp)

    def clear_storm(self, fingerprint: str | None) -> None:
        """解除风暴源标记（恢复后自动调用，也可外部调用）。

        同时重置该源窗口状态——否则残留计数立即再次触发风暴标记。
        """
        fp = fingerprint if fingerprint is not None else _UNKNOWN_SOURCE
        self._storm_sources.discard(fp)
        self._source_windows.pop(fp, None)

    def is_storm_source(self, fingerprint: str | None) -> bool:
        """查询是否风暴源（供 get_stats 与外部查询）。"""
        fp = fingerprint if fingerprint is not None else _UNKNOWN_SOURCE
        return fp in self._storm_sources

    def get_storm_sources(self) -> set[str]:
        """查询全部风暴源指纹（副本）。"""
        return set(self._storm_sources)

    def get_once_fired_count(self) -> int:
        """查询已触发 ONCE 的源数量。"""
        return len(self._once_fired)

    def _storm_threshold_for(self, level: ErrorLevel) -> int:
        """风暴检测阈值 = max(该级计数阈值 × 10, storm_min_threshold)。

        计数阈值=0（禁用计数升级）时 storm_min_threshold（默认 100）
        保证风暴检测仍有效（spec §5.4.1 规则 3，P2-3 修复）。
        """
        threshold = 0
        if level is ErrorLevel.WARN:
            threshold = self._config.warn_error_threshold
        elif level is ErrorLevel.ERROR:
            threshold = self._config.error_critical_threshold
        elif level is ErrorLevel.CRITICAL:
            threshold = self._config.critical_fatal_threshold
        return max(threshold * 10, self._config.storm_min_threshold)
