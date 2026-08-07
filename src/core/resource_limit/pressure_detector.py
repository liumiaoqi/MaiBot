"""PressureDetector — 压力分级引擎，对标 Linux vmpressure。

基于"请求量/成功量"比率与窗口累计计算资源压力等级，
三重判定（窗口累计 + 比率算法 + 优先级兜底）+ 滞回状态机。
"""


from src.common.logger import get_logger
import time
from typing import Any, Optional

from src.core.resource_limit.types import PressureLevel

logger = get_logger(__name__)

# 滞回阈值（比率百分比）
_RATIO_UP_CRITICAL = 95.0
_RATIO_UP_MEDIUM = 60.0
_RATIO_DOWN_MEDIUM = 85.0
_RATIO_DOWN_LOW = 50.0

# 默认窗口大小（对标 vmpressure_win = 512）
_DEFAULT_WIN_SIZE = 512

# 优先级紧急阈值（≤3 强制 CRITICAL）
_PRIORITY_CRITICAL_THRESHOLD = 3


def get_psi_summary() -> Optional[dict[str, dict[str, float]]]:
    """读取 /proc/pressure/{memory,cpu,io} PSI 摘要。

    Linux 4.20+ 原生 PSI，6.18 内核必有。
    文件不存在或读取失败时返回 None（可选字段）。

    ZG-5 应用层消费 OS 信号，不给 ZG-9 加接口负担（design §3.3.2）。
    """
    summary: dict[str, dict[str, float]] = {}
    for resource in ("memory", "cpu", "io"):
        path = f"/proc/pressure/{resource}"
        try:
            with open(path, "r") as f:
                line = f.readline().strip()
            # 格式: "some avg10=0.00 avg60=0.00 avg300=0.00 total=0"
            parts = line.split()
            entry: dict[str, float] = {}
            for part in parts[1:]:  # 跳过 "some"/"full"
                if "=" in part:
                    key, val = part.split("=", 1)
                    if key in ("avg10", "avg60", "avg300"):
                        entry[key] = float(val)
            if entry:
                summary[resource] = entry
        except (FileNotFoundError, PermissionError, ValueError, OSError):
            continue

    return summary if summary else None


class PressureWindow:
    """压力采样窗口，对应 design §3.3.2。"""

    def __init__(self, win_size: int = _DEFAULT_WIN_SIZE):
        self.scanned: int = 0
        self.reclaimed: int = 0
        self.win_size = win_size
        self.current_level: PressureLevel = PressureLevel.LOW

    def reset(self) -> None:
        """窗口清零。"""
        self.scanned = 0
        self.reclaimed = 0

    def is_full(self) -> bool:
        """窗口是否已满。"""
        return self.scanned >= self.win_size

    def set_state(self, scanned: int, reclaimed: int, level: PressureLevel) -> None:
        """供测试注入。"""
        self.scanned = scanned
        self.reclaimed = reclaimed
        self.current_level = level


class PressureDetector:
    """压力分级引擎，对应 design §3.3。

    三重判定：窗口累计 + 比率算法 + 优先级兜底。
    等级变更时通过 emit_sync 发布 resource.pressure.{level} 事件。
    """

    def __init__(
        self,
        event_bus: Any = None,
        win_size: int = _DEFAULT_WIN_SIZE,
        priority_critical_threshold: int = _PRIORITY_CRITICAL_THRESHOLD,
    ):
        self._window = PressureWindow(win_size)
        self._event_bus = event_bus
        self._priority_critical_threshold = priority_critical_threshold

    @property
    def current_level(self) -> PressureLevel:
        return self._window.current_level

    @property
    def window(self) -> PressureWindow:
        return self._window

    def record_sample(
        self, scanned_delta: int, reclaimed_delta: int, scan_priority: int = 12
    ) -> Optional[PressureLevel]:
        """记录压力采样，对应 design §3.3.3。

        Args:
            scanned_delta: 请求量增量（charge 拒绝时 +1）
            reclaimed_delta: 成功量增量（charge 成功时 +1）
            scan_priority: 扫描优先级，≤threshold 强制 CRITICAL

        Returns:
            等级变更时返回新等级，未变更或窗口未满时返回 None
        """
        self._window.scanned += scanned_delta
        self._window.reclaimed += reclaimed_delta

        # 判定 1：窗口未满 且 优先级非紧急 → 不计算
        if not self._window.is_full() and scan_priority > self._priority_critical_threshold:
            return None

        # 判定 2：优先级兜底 → 强制 CRITICAL
        if scan_priority <= self._priority_critical_threshold:
            new_level = PressureLevel.CRITICAL
        else:
            # 判定 3：比率算法
            new_level = self._calc_ratio_level()

        # 滞回判定
        changed_level = self._hysteresis_judge(new_level)

        if changed_level is not None:
            self._window.current_level = changed_level
            self._emit_pressure_event(changed_level)

        # 窗口清零
        self._window.reset()

        return changed_level

    def _calc_ratio_level(self) -> PressureLevel:
        """比率算法，对应 spec §5.3.1.2。"""
        if self._window.scanned == 0:
            return PressureLevel.LOW

        ratio = (self._window.scanned - self._window.reclaimed) / self._window.scanned * 100

        if ratio >= _RATIO_UP_CRITICAL:
            return PressureLevel.CRITICAL
        elif ratio >= _RATIO_UP_MEDIUM:
            return PressureLevel.MEDIUM
        else:
            return PressureLevel.LOW

    def _hysteresis_judge(self, new_level: PressureLevel) -> Optional[PressureLevel]:
        """滞回判定，对应 design §3.3.3 滞回判定逻辑。

        升级用升级阈值（已在比率计算中应用）。
        降级用降级阈值（需重新计算比率对照降级阈值）。
        """
        current = self._window.current_level

        if new_level == current:
            return None  # 无变更

        if self._level_value(new_level) > self._level_value(current):
            # 升级：直接返回（升级阈值已在比率计算中应用）
            return new_level
        else:
            # 降级：用降级阈值判定
            if self._window.scanned == 0:
                return new_level

            ratio = (self._window.scanned - self._window.reclaimed) / self._window.scanned * 100

            if current == PressureLevel.CRITICAL and ratio < _RATIO_DOWN_MEDIUM:
                return PressureLevel.MEDIUM
            if current == PressureLevel.MEDIUM and ratio < _RATIO_DOWN_LOW:
                return PressureLevel.LOW
            if current == PressureLevel.CRITICAL and ratio < _RATIO_DOWN_LOW:
                return PressureLevel.LOW

            return None  # 未达降级阈值，保持

    @staticmethod
    def _level_value(level: PressureLevel) -> int:
        """等级数值化，用于比较。"""
        return {PressureLevel.LOW: 0, PressureLevel.MEDIUM: 1, PressureLevel.CRITICAL: 2}[level]

    def _emit_pressure_event(self, level: PressureLevel) -> None:
        """发布压力事件，对应 spec §5.3.1.5。

        事件数据结构: {level: str, timestamp: float, psi_summary: dict (可选)}
        热路径用 emit_sync 避免协程调度开销。
        """
        event_type = f"resource.pressure.{level.value}"
        event_data = {
            "level": level.value,
            "timestamp": time.monotonic(),
            "psi_summary": get_psi_summary(),
        }

        if self._event_bus is not None:
            try:
                self._event_bus.emit_sync(event_type, event_data)
            except Exception as e:
                from src.core.error_escalation.types import ErrorLevel
                from src.core.error_escalation_port_registry import get_error_escalation_port
                port = get_error_escalation_port()
                if port is not None:
                    port.report(ErrorLevel.WARNING, "压力事件发布失败，压力分级继续工作", exception=e)
                from src.core.tainted_mask.mark import mark_exception_swallowed
                mark_exception_swallowed()
                logger.error("压力事件发布失败，压力分级继续工作: %s", e)
