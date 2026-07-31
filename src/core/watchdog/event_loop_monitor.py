"""事件循环阻塞检测引擎。

touch 时间戳刷新（主循环协程）+ 独立线程周期检测 + 双层判定 + 连续计数 + 冷却窗口 + 恢复检测。
纯内存操作，检测线程独立于事件循环。
"""


import asyncio
import logging
import threading
import time
from typing import Callable, Optional

from src.core.watchdog.config import WatchdogConfig
from src.core.watchdog.types import BlockSeverity, FaultReason, FaultReportEvent, WatchdogStatus

logger = logging.getLogger(__name__)


class EventLoopMonitor:
    """事件循环阻塞检测引擎。

    touch 在主事件循环协程内刷新，检测在独立 threading.Thread 跑（不依赖事件循环调度）。
    双层判定：轻度卡顿（mild_threshold_s）仅告警，严重阻塞（severe_threshold_s）连续 N 次后上报。
    """

    def __init__(
        self,
        config: WatchdogConfig,
        main_loop: asyncio.AbstractEventLoop,
        report_callback: Callable[[FaultReportEvent], None],
    ) -> None:
        self._config = config
        self._main_loop = main_loop
        self._report_callback = report_callback

        self._touch_lock = threading.Lock()
        self._last_touch_time: float = 0.0

        self._stop_event = threading.Event()
        self._detect_thread: Optional[threading.Thread] = None

        self._block_severity = BlockSeverity.NORMAL
        self._last_check_time: float = 0.0
        self._consecutive_severe_count: int = 0
        self._cooldown_until: float = 0.0
        self._total_mild_lag_count: int = 0
        self._total_severe_report_count: int = 0
        self._check_period_no: int = 0

    def touch(self) -> None:
        """刷新事件循环存活时间戳（由主循环协程以 ≤1s 间隔调用）。"""
        now = time.monotonic()
        with self._touch_lock:
            self._last_touch_time = now

    def start(self) -> None:
        """启动检测线程。"""
        with self._touch_lock:
            self._last_touch_time = time.monotonic()
        self._stop_event.clear()
        self._detect_thread = threading.Thread(
            target=self._detect_loop, daemon=True, name="watchdog-detect"
        )
        self._detect_thread.start()
        logger.info("事件循环检测线程已启动")

    def stop(self) -> None:
        """停止检测线程（等待最多 10s）。"""
        self._stop_event.set()
        if self._detect_thread is not None:
            self._detect_thread.join(timeout=10)
            if self._detect_thread.is_alive():
                logger.warning("检测线程未在 10s 内退出")
            self._detect_thread = None
        logger.info("事件循环检测线程已停止")

    def _detect_loop(self) -> None:
        """独立线程主循环，按 check_interval_s 间隔周期检测。"""
        while not self._stop_event.is_set():
            if self._stop_event.wait(self._config.check_interval_s):
                break
            try:
                self._detect_once()
            except Exception:
                logger.exception("检测周期发生异常，跳过本次判定")

    def _detect_once(self) -> None:
        """单次检测判定逻辑。"""
        with self._touch_lock:
            last_touch = self._last_touch_time

        now = time.monotonic()
        elapsed = now - last_touch

        if elapsed < 0:
            logger.warning(
                "touch 时间戳回跳（elapsed=%.3fs），已忽略本次判定", elapsed
            )
            return

        self._check_period_no += 1
        self._last_check_time = now

        if elapsed < self._config.mild_threshold_s:
            self._handle_normal()
        elif elapsed < self._config.severe_threshold_s:
            self._handle_mild_lag(elapsed)
        else:
            self._handle_severe_block(elapsed)

    def _handle_normal(self) -> None:
        """正常判定：重置连续计数，检测恢复。"""
        was_severe = self._block_severity == BlockSeverity.SEVERE_BLOCK
        was_in_cooldown = self._is_in_cooldown()
        if was_severe or was_in_cooldown:
            logger.info(
                "阻塞恢复（check_period=%d, total_mild=%d, total_severe_report=%d）",
                self._check_period_no,
                self._total_mild_lag_count,
                self._total_severe_report_count,
            )
            self._cooldown_until = 0.0
        self._block_severity = BlockSeverity.NORMAL
        self._consecutive_severe_count = 0

    def _handle_mild_lag(self, elapsed: float) -> None:
        """轻度卡顿判定：告警日志，不触发上报、不增加连续计数。"""
        self._block_severity = BlockSeverity.MILD_LAG
        self._total_mild_lag_count += 1
        logger.warning(
            "事件循环轻度卡顿（elapsed=%.3fs, check_period=%d）",
            elapsed,
            self._check_period_no,
        )

    def _handle_severe_block(self, elapsed: float) -> None:
        """严重阻塞判定：连续计数，达阈值且不在冷却则上报。"""
        self._block_severity = BlockSeverity.SEVERE_BLOCK
        self._consecutive_severe_count += 1

        if self._is_in_cooldown():
            logger.warning(
                "持续阻塞(冷却中)（elapsed=%.3fs, consecutive=%d, check_period=%d）",
                elapsed,
                self._consecutive_severe_count,
                self._check_period_no,
            )
            return

        if self._consecutive_severe_count >= self._config.consecutive_report_threshold:
            self._report_severe_block(elapsed)
        else:
            logger.warning(
                "持续阻塞(未达上报条件)（elapsed=%.3fs, consecutive=%d/%d, check_period=%d）",
                elapsed,
                self._consecutive_severe_count,
                self._config.consecutive_report_threshold,
                self._check_period_no,
            )

    def _report_severe_block(self, elapsed: float) -> None:
        """构造故障事件并上报，进入冷却窗口。"""
        detail = (
            f"elapsed={elapsed:.3f}s, check_period={self._check_period_no}, "
            f"consecutive={self._consecutive_severe_count}"
        )
        event = FaultReportEvent(
            component_id="event_loop",
            reason=FaultReason.LOOP_BLOCKED,
            detail=detail,
            report_time=time.monotonic(),
            check_period_no=self._check_period_no,
        )
        self._report_callback(event)
        self._cooldown_until = time.monotonic() + self._config.cooldown_s
        self._total_severe_report_count += 1
        self._consecutive_severe_count = 0
        logger.warning(
            "严重阻塞上报（elapsed=%.3fs, check_period=%d, cooldown=%.1fs）",
            elapsed,
            self._check_period_no,
            self._config.cooldown_s,
        )

    def _is_in_cooldown(self) -> bool:
        """是否在冷却窗口内。"""
        return time.monotonic() < self._cooldown_until

    def get_status(self) -> WatchdogStatus:
        """返回当前状态快照（纯内存聚合无 I/O）。"""
        with self._touch_lock:
            last_touch = self._last_touch_time
        return WatchdogStatus(
            block_severity=self._block_severity,
            last_touch_time=last_touch,
            last_check_time=self._last_check_time,
            consecutive_severe_count=self._consecutive_severe_count,
            cooldown_until=self._cooldown_until,
            total_mild_lag_count=self._total_mild_lag_count,
            total_severe_report_count=self._total_severe_report_count,
            check_period_no=self._check_period_no,
        )