"""Runner 健康桥接引擎。

V2 回调桥接（订阅 timeout_callback + 轮询 get_health_status diff）+
V1 旁路轮询（进程存活 + 重启计数 diff）+ 上报限流 + 恢复信号处理。
桥接非重检，不重新实现检测。
"""


import asyncio
import time
from typing import Any, Awaitable, Callable, Optional

from src.common.logger import get_logger
from src.core.service_manager_port_registry import get_service_manager_port
from src.core.watchdog.config import WatchdogConfig
from src.core.watchdog.exceptions import UnknownRunnerError
from src.core.watchdog.types import (
    DetectionSource,
    FaultReason,
    FaultReportEvent,
    RunnerBridgeStatus,
)

logger = get_logger(__name__)


class RunnerHealthBridge:
    """Runner 健康桥接引擎。

    V2 桥接在主循环内执行（asyncio.Task + asyncio.sleep），直接 await 上报回调。
    V1 旁路轮询同样在主循环内执行，不额外起线程。
    """

    def __init__(
        self,
        config: WatchdogConfig,
        main_loop: asyncio.AbstractEventLoop,
        report_callback: Callable[[FaultReportEvent], Awaitable[None]],
    ) -> None:
        self._config = config
        self._main_loop = main_loop
        self._report_callback = report_callback

        self._bridge_status: dict[str, RunnerBridgeStatus] = {}
        self._v2_supervisors: dict[str, tuple[Any, Any]] = {}
        self._v1_supervisors: dict[str, Any] = {}
        self._last_restart_count: dict[str, int] = {}
        self._poll_tasks: dict[str, asyncio.Task] = {}
        self._skip_warning_logged: set[str] = set()

    def register_v2_supervisor(
        self,
        runner_id: str,
        supervisor: Any,
        heartbeat_manager: Any,
        component_id: str,
    ) -> None:
        """注册 V2 RunnerSupervisor + HeartbeatManager 供桥接订阅。"""
        if runner_id in self._v2_supervisors:
            logger.info(
                "V2 Runner 已注册，忽略重复注册（runner_id=%s）", runner_id
            )
            return
        if not hasattr(supervisor, "get_health_status"):
            raise ValueError(
                f"V2 supervisor 缺少 get_health_status() 方法: {runner_id}"
            )

        self._bridge_status[runner_id] = RunnerBridgeStatus(
            runner_id=runner_id,
            component_id=component_id,
            last_detection_source=DetectionSource.HEARTBEAT,
            last_consecutive_failures=0,
            cooldown_until=0.0,
            total_report_count=0,
            last_report_time=0.0,
            is_recovering=False,
        )
        self._v2_supervisors[runner_id] = (supervisor, heartbeat_manager)

        # 注入心跳超时旁路监听器（FR-1 根因修复），不依赖 start 已调用；
        # heartbeat_manager 缺该方法时防御性降级，不阻断桥接其余能力
        try:
            heartbeat_manager.add_timeout_listener(runner_id, self._on_v2_timeout)
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.ERROR, 'V2 心跳监听器注入失败，已降级跳过', exception=exc)
            from src.core.tainted_mask.mark import mark_exception_swallowed
            mark_exception_swallowed()
            logger.exception(
                "V2 心跳监听器注入失败，已降级跳过（runner_id=%s）", runner_id
            )

        task = asyncio.ensure_future(
            self._v2_diff_loop(runner_id), loop=self._main_loop
        )
        task.set_name(f"watchdog-v2-diff-{runner_id}")
        self._poll_tasks[runner_id] = task
        logger.info("已注册 V2 Runner 桥接: %s (component_id=%s)", runner_id, component_id)

    async def _on_v2_timeout(
        self, runner_id: str, context: Optional[dict[str, Any]] = None
    ) -> None:
        """V2 心跳超时回调处理。"""
        try:
            consecutive_failures = 0
            if context:
                consecutive_failures = context.get("consecutive_failures", 0)
            await self._report_runner_unresponsive(
                runner_id, DetectionSource.HEARTBEAT, consecutive_failures
            )
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.ERROR, 'V2 超时回调处理异常', exception=exc)
            from src.core.tainted_mask.mark import mark_exception_swallowed
            mark_exception_swallowed()
            logger.exception("V2 超时回调处理异常（runner_id=%s）", runner_id)

    async def _v2_diff_loop(self, runner_id: str) -> None:
        """V2 状态 diff 轮询循环。"""
        try:
            while runner_id in self._v2_supervisors:
                await asyncio.sleep(self._config.v2_diff_interval_s)
                if runner_id not in self._v2_supervisors:
                    return

                entry = self._v2_supervisors.get(runner_id)
                if entry is None:
                    return
                supervisor, _ = entry
                try:
                    health_status = supervisor.get_health_status()
                    runner_status = health_status.get(runner_id)
                    if runner_status is None:
                        continue

                    status_value = getattr(runner_status, "status", None)
                    if status_value is not None:
                        status_str = getattr(status_value, "value", str(status_value))
                    else:
                        status_str = ""

                    if status_str in ("failed", "zombie"):
                        source = DetectionSource.PROCESS_POLL
                        reason = getattr(runner_status, "last_failure_reason", "")
                        if reason and "registry" in str(reason).lower():
                            source = DetectionSource.REGISTRY
                        await self._report_runner_unresponsive(runner_id, source, 1)
                    elif status_str == "running":
                        await self._on_runner_recovered(runner_id)
                except Exception as exc:
                    from src.core.error_escalation.types import ErrorLevel
                    from src.core.error_escalation_port_registry import get_error_escalation_port
                    port = get_error_escalation_port()
                    if port is not None:
                        port.report(ErrorLevel.ERROR, 'V2 diff 轮询异常', exception=exc)
                    from src.core.tainted_mask.mark import mark_exception_swallowed
                    mark_exception_swallowed()
                    logger.exception("V2 diff 轮询异常（runner_id=%s）", runner_id)
        except asyncio.CancelledError:
            # P0-4: 正常取消静默（防刷屏，对标 kernel/signal.c TASK_KILLABLE）
            pass
        except Exception as exc:
            # P0-4: 关闭路径非预期异常出声（ZG-31）
            logger.exception("V2 diff 轮询循环异常（runner_id=%s）: %s", runner_id, exc, exc_info=True)

    def register_v1_supervisor(
        self,
        runner_id: str,
        supervisor: Any,
        component_id: str,
    ) -> None:
        """注册 V1 PluginRunnerSupervisor 供旁路轮询。"""
        if runner_id in self._v1_supervisors:
            logger.info(
                "V1 Runner 已注册，忽略重复注册（runner_id=%s）", runner_id
            )
            return
        if not hasattr(supervisor, "_runner_process") or not hasattr(
            supervisor, "_restart_count"
        ):
            raise ValueError(
                f"V1 supervisor 缺少 _runner_process 或 _restart_count 属性: {runner_id}"
            )

        self._bridge_status[runner_id] = RunnerBridgeStatus(
            runner_id=runner_id,
            component_id=component_id,
            last_detection_source=DetectionSource.PROCESS_POLL,
            last_consecutive_failures=0,
            cooldown_until=0.0,
            total_report_count=0,
            last_report_time=0.0,
            is_recovering=False,
        )
        self._v1_supervisors[runner_id] = supervisor
        self._last_restart_count[runner_id] = getattr(supervisor, "_restart_count", 0)

        task = asyncio.ensure_future(
            self._v1_poll_loop(runner_id), loop=self._main_loop
        )
        task.set_name(f"watchdog-v1-poll-{runner_id}")
        self._poll_tasks[runner_id] = task
        logger.info("已注册 V1 Runner 桥接: %s (component_id=%s)", runner_id, component_id)

    async def _v1_poll_loop(self, runner_id: str) -> None:
        """V1 旁路轮询循环。"""
        try:
            while runner_id in self._v1_supervisors:
                await asyncio.sleep(self._config.v1_poll_interval_s)
                if runner_id not in self._v1_supervisors:
                    return

                supervisor = self._v1_supervisors.get(runner_id)
                if supervisor is None:
                    return

                try:
                    process = getattr(supervisor, "_runner_process", None)
                    if process is None:
                        if runner_id not in self._skip_warning_logged:
                            self._skip_warning_logged.add(runner_id)
                            logger.warning(
                                "V1 supervisor._runner_process 属性缺失，跳过本轮轮询（runner_id=%s，后续静默）",
                                runner_id,
                            )
                    else:
                        returncode = getattr(process, "returncode", None)
                        if returncode is not None:
                            await self._report_runner_unresponsive(
                                runner_id, DetectionSource.PROCESS_POLL, 1
                            )
                            continue

                    last_count = self._last_restart_count.get(runner_id, 0)
                    current_count = getattr(supervisor, "_restart_count", last_count)
                    diff = current_count - last_count
                    if diff > 0:
                        self._last_restart_count[runner_id] = current_count
                        await self._report_runner_unresponsive(
                            runner_id, DetectionSource.PROCESS_POLL, diff
                        )
                        continue

                    if process is not None:
                        returncode = getattr(process, "returncode", None)
                        if returncode is None and diff == 0:
                            status = self._bridge_status.get(runner_id)
                            if status and status.is_recovering:
                                await self._on_runner_recovered(runner_id)
                except Exception as exc:
                    from src.core.error_escalation.types import ErrorLevel
                    from src.core.error_escalation_port_registry import get_error_escalation_port
                    port = get_error_escalation_port()
                    if port is not None:
                        port.report(ErrorLevel.ERROR, 'V1 旁路轮询异常', exception=exc)
                    from src.core.tainted_mask.mark import mark_exception_swallowed
                    mark_exception_swallowed()
                    logger.exception("V1 旁路轮询异常（runner_id=%s）", runner_id)
        except asyncio.CancelledError:
            # P0-4: 正常取消静默（防刷屏，对标 kernel/signal.c TASK_KILLABLE）
            pass
        except Exception as exc:
            # P0-4: 关闭路径非预期异常出声（ZG-31）
            logger.exception("V1 旁路轮询循环异常（runner_id=%s）: %s", runner_id, exc, exc_info=True)

    async def _report_runner_unresponsive(
        self,
        runner_id: str,
        source: DetectionSource,
        consecutive_failures: int,
    ) -> None:
        """上报 Runner 无响应（含限流与未纳入管理检查）。"""
        status = self._bridge_status.get(runner_id)
        if status is None:
            return

        now = time.monotonic()
        if now < status.cooldown_until:
            logger.warning(
                "Runner %s 持续无响应, 跳过上报(冷却中)", runner_id
            )
            return

        # blocker 追踪（ZG-3 补强 S4）：按检测来源填充阻塞源标识
        blocker_info = {
            DetectionSource.HEARTBEAT: "heartbeat_timeout",
            DetectionSource.PROCESS_POLL: "process_unresponsive",
            DetectionSource.REGISTRY: "registry_connection_failed",
        }.get(source, source.value)
        detail = (
            f"runner_id={runner_id}, source={source.value}, "
            f"consecutive_failures={consecutive_failures}, "
            f"check_period={status.total_report_count}, "
            f"blocker_info={blocker_info}"
        )
        event = FaultReportEvent(
            component_id=status.component_id,
            reason=FaultReason.RUNNER_UNRESPONSIVE,
            detail=detail,
            report_time=now,
            check_period_no=status.total_report_count,
            blocker_info=blocker_info,
        )

        sm_port = get_service_manager_port()
        if sm_port is None:
            if runner_id not in self._skip_warning_logged:
                self._skip_warning_logged.add(runner_id)
                logger.warning(
                    "ServiceManagerPort 未注册，跳过 Runner %s 上报（后续静默）", runner_id
                )
            return
        component_state = sm_port.get_state(status.component_id)
        if component_state is None:
            if runner_id not in self._skip_warning_logged:
                self._skip_warning_logged.add(runner_id)
                logger.warning(
                    "Runner %s 未纳入服务管理器，跳过上报（component_id=%s，后续静默）",
                    runner_id,
                    status.component_id,
                )
            return

        try:
            await self._report_callback(event)
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.ERROR, 'Runner 上报回调异常', exception=exc)
            from src.core.tainted_mask.mark import mark_exception_swallowed
            mark_exception_swallowed()
            logger.exception("Runner 上报回调异常（runner_id=%s）", runner_id)
            return

        self._bridge_status[runner_id] = RunnerBridgeStatus(
            runner_id=runner_id,
            component_id=status.component_id,
            last_detection_source=source,
            last_consecutive_failures=consecutive_failures,
            cooldown_until=time.monotonic() + self._config.cooldown_s,
            total_report_count=status.total_report_count + 1,
            last_report_time=time.monotonic(),
            is_recovering=False,
        )
        self._skip_warning_logged.discard(runner_id)

    async def _on_runner_recovered(self, runner_id: str) -> None:
        """处理 Runner 恢复信号。"""
        status = self._bridge_status.get(runner_id)
        if status is None:
            return
        if status.total_report_count == 0 and not status.is_recovering:
            logger.warning(
                "Runner %s 收到未预期的恢复信号，已忽略", runner_id
            )
            return

        logger.info("Runner %s 恢复", runner_id)
        self._bridge_status[runner_id] = RunnerBridgeStatus(
            runner_id=runner_id,
            component_id=status.component_id,
            last_detection_source=status.last_detection_source,
            last_consecutive_failures=0,
            cooldown_until=0.0,
            total_report_count=status.total_report_count,
            last_report_time=status.last_report_time,
            is_recovering=False,
        )

    def unregister_runner(self, runner_id: str) -> None:
        """取消注册 Runner。"""
        if runner_id not in self._bridge_status:
            raise UnknownRunnerError(runner_id)

        # V2 条目先摘除心跳超时监听器（与 heartbeat_mgr.stop 的清理语义配套）
        entry = self._v2_supervisors.get(runner_id)
        if entry is not None:
            _, heartbeat_manager = entry
            try:
                heartbeat_manager.remove_timeout_listener(
                    runner_id, self._on_v2_timeout
                )
            except Exception as exc:
                from src.core.error_escalation.types import ErrorLevel
                from src.core.error_escalation_port_registry import get_error_escalation_port
                port = get_error_escalation_port()
                if port is not None:
                    port.report(ErrorLevel.ERROR, 'V2 心跳监听器摘除失败，已降级跳过', exception=exc)
                from src.core.tainted_mask.mark import mark_exception_swallowed
                mark_exception_swallowed()
                logger.exception(
                    "V2 心跳监听器摘除失败，已降级跳过（runner_id=%s）", runner_id
                )

        task = self._poll_tasks.pop(runner_id, None)
        if task is not None:
            task.cancel()
        self._bridge_status.pop(runner_id, None)
        self._v2_supervisors.pop(runner_id, None)
        self._v1_supervisors.pop(runner_id, None)
        self._last_restart_count.pop(runner_id, None)
        logger.info("已取消注册 Runner 桥接: %s", runner_id)

    def get_runner_bridge_status(self, runner_id: str) -> Optional[RunnerBridgeStatus]:
        """返回单个 Runner 桥接状态快照。"""
        return self._bridge_status.get(runner_id)

    def list_runner_bridge_status(self) -> list[RunnerBridgeStatus]:
        """返回全部 Runner 桥接状态快照。"""
        return list(self._bridge_status.values())

    async def stop(self) -> None:
        """停止全部轮询任务，清空注册表。"""
        for runner_id in list(self._poll_tasks.keys()):
            task = self._poll_tasks.pop(runner_id, None)
            if task is not None:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    # P0-4: 正常取消静默（防刷屏，对标 kernel/signal.c TASK_KILLABLE）
                    pass
                except Exception as exc:
                    # P0-4: 关闭路径非预期异常出声（ZG-31）
                    logger.warning("poll_task 关闭异常（runner_id=%s）: %s", runner_id, exc, exc_info=True)
        self._bridge_status.clear()
        self._v2_supervisors.clear()
        self._v1_supervisors.clear()
        self._last_restart_count.clear()
