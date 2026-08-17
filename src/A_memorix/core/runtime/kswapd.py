"""ZG-27 后台回收任务（对标 Linux mm/vmscan.c:7399 kswapd 主循环）。

Linux 源码参考：
- mm/vmscan.c:7399 — kswapd 主循环
- mm/vmscan.c:7431-7432 — kswapd_try_sleep 检查间隔
- mm/vmscan.c:7064 — balance_pgdat priority 递减循环
- mm/vmscan.c:7102 — sc.priority = DEF_PRIORITY 起始
- mm/vmscan.c:6991 — kswapd_shrink_node 回收目标=high 水位
"""

import asyncio

from src.A_memorix.core.runtime.reclaim_scheduler import ReclaimScheduler
from src.A_memorix.core.runtime.watermark import WatermarkState, WatermarkZone
from src.common.logger import get_logger

logger = get_logger("a_memorix.kswapd")


class MemoryKswapd:
    """后台回收任务（对标 Linux mm/vmscan.c:7399 kswapd 主循环）。

    每 check_interval_sec 检查水位，LOW 唤醒 → priority 递减循环 → 回收到 HIGH 休眠。
    异常不崩溃——双通道上报（logger + error_escalation_port），下一轮继续（spec 5.1.3 异常场景 2）。
    """

    def __init__(
        self,
        watermark_zone: WatermarkZone,
        reclaim_scheduler: ReclaimScheduler,
        background_scheduler,
        error_port=None,
    ) -> None:
        self._zone = watermark_zone
        self._scheduler = reclaim_scheduler
        self._background_scheduler = background_scheduler
        self._error_port = error_port

    def _report_warning(self, msg: str, exc: Exception) -> None:
        """双通道上报：logger + error_escalation_port（P2-7 修复）。"""
        logger.warning("%s: %s", msg, exc, exc_info=True)
        if self._error_port is not None:
            try:
                self._error_port.report_warning(f"kswapd: {msg}", exception=exc)
            except Exception:
                logger.debug("error_escalation_port 上报失败，已忽略")

    async def run(self) -> None:
        """kswapd 主循环（对标 vmscan.c:7399）。

        每 check_interval_sec 检查水位，BELOW_LOW 唤醒回收，ABOVE_HIGH 休眠。
        """
        try:
            while not self._background_scheduler.stopping:
                interval = self._zone._config.check_interval_sec
                await asyncio.sleep(interval)
                if self._background_scheduler.stopping:
                    break
                try:
                    await self._run_one_cycle()
                except Exception as exc:
                    self._report_warning("kswapd 回收异常", exc)
        except asyncio.CancelledError:
            raise

    async def _run_one_cycle(self) -> None:
        """单轮回收：检查水位 → BELOW_LOW 时 priority 递减循环回收 → ABOVE_HIGH 退出。"""
        try:
            state = self._zone.state()
        except Exception as exc:
            self._report_warning("kswapd 水位检查异常", exc)
            return
        if state == WatermarkState.ABOVE_HIGH:
            return
        # BELOW_LOW / BETWEEN → priority 递减循环回收（对标 vmscan.c:7064 balance_pgdat）
        priority = self._scheduler.config.def_priority  # DEF_PRIORITY 起始（对标 vmscan.c:7102）
        while priority >= 1 and not self._background_scheduler.stopping:
            await self._scheduler.run_reclaim(priority=priority)
            try:
                state = self._zone.state()
            except Exception as exc:
                self._report_warning("kswapd 水位检查异常", exc)
                break
            if state == WatermarkState.ABOVE_HIGH:
                break
            priority -= 1