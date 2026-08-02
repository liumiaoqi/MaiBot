"""WatchdogAdapter — 实现 WatchdogPort，组装 EventLoopMonitor + RunnerHealthBridge。

适配器层，唯一允许导入具体引擎类的地方。经 ServiceManagerPort 上报故障。
"""


import asyncio
import time
from typing import Any, Callable, Optional

from src.core.protocols import WatchdogPort
from src.core.service_manager_port_registry import get_service_manager_port
from src.core.watchdog.config import WatchdogConfig
from src.core.watchdog.event_loop_monitor import EventLoopMonitor
from src.core.watchdog.exceptions import (
    ServiceManagerPortNotReadyError,
    WatchdogAlreadyRunningError,
)
from src.core.watchdog.runner_health_bridge import RunnerHealthBridge
from src.core.watchdog.types import (
    BlockSeverity,
    FaultReportEvent,
    RunnerBridgeStatus,
    WatchdogStatus,
)

from src.common.logger import get_logger

logger = get_logger(__name__)


class WatchdogAdapter(WatchdogPort):
    """看门狗适配器 — 组装检测引擎 + 桥接引擎，经 ServiceManagerPort 上报。"""

    def __init__(self, config: WatchdogConfig) -> None:
        self._config = config
        self._event_loop_monitor: Optional[EventLoopMonitor] = None
        self._runner_bridge: Optional[RunnerHealthBridge] = None
        self._main_loop: Optional[asyncio.AbstractEventLoop] = None
        self._running: bool = False
        self._status_subscribers: list[Callable[[WatchdogStatus], None]] = []
        self._timeout_subscribers: list[Callable[[FaultReportEvent], None]] = []

    async def start(self, main_loop: asyncio.AbstractEventLoop) -> None:
        """启动看门狗。"""
        if self._running:
            raise WatchdogAlreadyRunningError("看门狗已在运行")

        sm_port = get_service_manager_port()
        if sm_port is None:
            raise ServiceManagerPortNotReadyError(
                "ServiceManagerPort 未注册，无法启动看门狗"
            )

        self._main_loop = main_loop
        self._event_loop_monitor = EventLoopMonitor(
            self._config, main_loop, self._sync_report_callback
        )
        self._runner_bridge = RunnerHealthBridge(
            self._config, main_loop, self._async_report_callback
        )

        self._event_loop_monitor.start()
        self._running = True
        logger.info("看门狗已启动")

    async def stop(self) -> None:
        """停止看门狗。"""
        if self._event_loop_monitor is not None:
            self._event_loop_monitor.stop()
        if self._runner_bridge is not None:
            await self._runner_bridge.stop()
        self._running = False
        logger.info("看门狗已停止")

    def touch(self, delay: bool = False) -> None:
        """刷新事件循环存活时间戳。

        Args:
            delay: 是否标记延迟报告（ZG-3 补强 S1），透传至 EventLoopMonitor。

        顺带执行检测线程健康检查（ZG-3 补强 S2）：主循环侧每 touch 间隔
        （≤1s）检查一次，频率足够且不额外起协程。
        """
        if self._event_loop_monitor is not None:
            self._event_loop_monitor.touch(delay)
            self._event_loop_monitor.check_detect_thread_health()

    def _sync_report_callback(self, event: FaultReportEvent) -> None:
        """供 EventLoopMonitor 检测线程调用，提交回主循环。"""
        if self._main_loop is None:
            return
        asyncio.run_coroutine_threadsafe(
            self._do_report(event), self._main_loop
        )
        asyncio.run_coroutine_threadsafe(
            self._notify_subscribers_async(), self._main_loop
        )

    async def _async_report_callback(self, event: FaultReportEvent) -> None:
        """供 RunnerHealthBridge 在主循环内调用。"""
        await self._do_report(event)
        await self._notify_subscribers_async()

    async def _do_report(self, event: FaultReportEvent) -> None:
        """经 ServiceManagerPort 上报故障 + 通知超时订阅者（ZG-8 force 触发）。"""
        self._notify_timeout_subscribers(event)
        sm_port = get_service_manager_port()
        if sm_port is None:
            logger.warning("ServiceManagerPort 未注册，跳过上报")
            return
        try:
            await sm_port.report_external_fault(
                event.component_id, event.reason.value, event.detail
            )
        except Exception:
            from src.core.tainted_mask.mark import mark_exception_swallowed
            mark_exception_swallowed()
            logger.exception("故障上报异常（component_id=%s）", event.component_id)

    async def _notify_subscribers_async(self) -> None:
        """向状态订阅者推送当前状态快照。"""
        if not self._status_subscribers:
            return
        if self._event_loop_monitor is None:
            return
        status = self._event_loop_monitor.get_status()
        for callback in self._status_subscribers:
            try:
                callback(status)
            except Exception:
                from src.core.tainted_mask.mark import mark_exception_swallowed
                mark_exception_swallowed()
                logger.warning("状态订阅回调异常", exc_info=True)

    def get_status(self) -> WatchdogStatus:
        """查询事件循环检测状态快照。"""
        if self._event_loop_monitor is None:
            return WatchdogStatus(
                block_severity=BlockSeverity.NORMAL,
                last_touch_time=0.0,
                last_check_time=0.0,
                consecutive_severe_count=0,
                cooldown_until=0.0,
                total_mild_lag_count=0,
                total_severe_report_count=0,
                check_period_no=0,
            )
        return self._event_loop_monitor.get_status()

    def get_runner_bridge_status(self, runner_id: str) -> Optional[RunnerBridgeStatus]:
        """查询单个 Runner 桥接状态快照。"""
        if self._runner_bridge is None:
            return None
        return self._runner_bridge.get_runner_bridge_status(runner_id)

    def list_runner_bridge_status(self) -> list[RunnerBridgeStatus]:
        """查询全部 Runner 桥接状态快照。"""
        if self._runner_bridge is None:
            return []
        return self._runner_bridge.list_runner_bridge_status()

    def list_blocked_runners(self) -> list[RunnerBridgeStatus]:
        """查询当前所有阻塞 Runner（ZG-5 OOM 受害者选择消费）。

        判定条件：cooldown_until > now。
        """

        if self._runner_bridge is None:
            return []
        now = time.monotonic()
        return [
            s
            for s in self._runner_bridge.list_runner_bridge_status()
            if s.cooldown_until > now
        ]

    def subscribe_timeout(
        self, callback: Callable[[FaultReportEvent], None]
    ) -> None:
        """订阅组件无响应超时事件（ZG-8 消费触发 force 通道）。

        故障上报路径（_do_report）在收到 FaultReportEvent 时同步通知已注册回调。
        """
        self._timeout_subscribers.append(callback)

    def unsubscribe_timeout(
        self, callback: Callable[[FaultReportEvent], None]
    ) -> None:
        """取消订阅。"""
        try:
            self._timeout_subscribers.remove(callback)
        except ValueError:
            pass

    def _notify_timeout_subscribers(self, event: FaultReportEvent) -> None:
        """通知超时订阅者（组件无响应类故障）。"""
        for callback in self._timeout_subscribers:
            try:
                callback(event)
            except Exception:
                from src.core.tainted_mask.mark import mark_exception_swallowed
                mark_exception_swallowed()
                logger.warning("超时订阅回调异常", exc_info=True)

    def subscribe_status_change(
        self, callback: Callable[[WatchdogStatus], None]
    ) -> None:
        """订阅检测状态变更事件。"""
        self._status_subscribers.append(callback)

    def unsubscribe_status_change(
        self, callback: Callable[[WatchdogStatus], None]
    ) -> None:
        """取消订阅。"""
        try:
            self._status_subscribers.remove(callback)
        except ValueError:
            pass

    def register_v2_supervisor(
        self,
        runner_id: str,
        supervisor: Any,
        heartbeat_manager: Any,
        component_id: str = "",
    ) -> None:
        """注册 V2 RunnerSupervisor + HeartbeatManager 供桥接订阅。"""
        if self._runner_bridge is None:
            raise RuntimeError("看门狗未启动")
        self._runner_bridge.register_v2_supervisor(
            runner_id, supervisor, heartbeat_manager, component_id or runner_id
        )

    def register_v1_supervisor(
        self,
        runner_id: str,
        supervisor: Any,
        component_id: str = "",
    ) -> None:
        """注册 V1 PluginRunnerSupervisor 供旁路轮询。"""
        if self._runner_bridge is None:
            raise RuntimeError("看门狗未启动")
        self._runner_bridge.register_v1_supervisor(
            runner_id, supervisor, component_id or runner_id
        )

    def unregister_runner(self, runner_id: str) -> None:
        """取消注册 Runner。"""
        if self._runner_bridge is None:
            raise RuntimeError("看门狗未启动")
        self._runner_bridge.unregister_runner(runner_id)
