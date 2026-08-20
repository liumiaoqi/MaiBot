"""错误升级梯 — 核心引擎 ErrorEscalator（ZG-14）。

集成升级判定（开关升级→计数升级双重驱动）+ 动作分派（同步先异步后）+
嵌套防护（_fatal_in_progress，对标 Linux oops_in_progress）+
事件广播。全程不杀进程（N2 裁决）：最高动作 STOP_CORE 优雅停机，
禁止 os._exit / sys.exit / os.kill（spec §5.3.1 规则 12）。

动作分派顺序（spec §5.3.1 规则 11）：
- 同步：LOG（CRITICAL/FATAL 前调 RateLimiterPort.set_min_level 突破
  抑制，P1-5 Suppressor 联动）/ TAINT / COUNT（升级判定已递增）
- 异步：DEGRADE / REPORT_FAULT / CRASH_DUMP / RESTART_COMPONENT /
  STOP_CORE 经 create_task 派发不阻塞；NOTIFY 用 emit_sync（design
  §2.2.2.2 衔接表，仅 CRITICAL/FATAL，spec §4.3 规则 3）
"""

import asyncio
import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from src.common.logger import get_logger
from src.core.control_message.types import ControlMessageKind
from src.core.error_escalation.config import ErrorEscalationConfig
from src.core.error_escalation.counter import ErrorCounter
from src.core.error_escalation.storm import StormDecision, StormTracker
from src.core.error_escalation.types import ErrorAction, ErrorLevel
from src.core.service_manager.types import SystemHealthLevel
from src.core.tainted_mask.taint_flag import TaintFlag

logger = get_logger("error_escalation")

# LOG 动作的日志级别映射。值取 Python stdlib logging 级别号
# （WARNING=30 / ERROR=40 / CRITICAL=50，稳定不变）；Python logging 无
# FATAL 级，FATAL 映射 CRITICAL（spec §5.3.1 规则 2）。不直接 import
# logging——ZG-2 受控规则（TID251），仅需级别常量时本地定义。
_LEVEL_WARNING = 30
_LEVEL_ERROR = 40
_LEVEL_CRITICAL = 50

_LOG_LEVELS: dict[ErrorLevel, int] = {
    ErrorLevel.WARN: _LEVEL_WARNING,
    ErrorLevel.ERROR: _LEVEL_ERROR,
    ErrorLevel.CRITICAL: _LEVEL_CRITICAL,
    ErrorLevel.FATAL: _LEVEL_CRITICAL,
}

# TAINT 动作的默认污染标志（spec §5.3.1 规则 3）
_DEFAULT_TAINT_FLAGS: dict[ErrorLevel, TaintFlag] = {
    ErrorLevel.WARN: TaintFlag.TAINT_WARN,
    ErrorLevel.ERROR: TaintFlag.TAINT_EXCEPTION_SWALLOWED,
}

# CRASH_DUMP 独立限流：默认 1 分钟最多 3 次（spec §5.5.1 规则 4）
_CRASH_DUMP_WINDOW_SEC = 60.0
_CRASH_DUMP_MAX_EXPORTS = 3


@dataclass(frozen=True)
class ErrorReport:
    """单次上报请求（spec §6.4，生命周期仅一次 report 调用）。

    level 缺失按 WARN 兜底（spec §5.1.3 异常场景 2）；component_id
    缺失时跳过 REPORT_FAULT / RESTART_COMPONENT（spec §5.1.1 规则 4）。
    """

    level: ErrorLevel | None = None
    message: str = ""
    component_id: str | None = None
    exception: Exception | None = None
    taint_flag: TaintFlag | None = None
    once: bool = False


@dataclass(frozen=True)
class ErrorEscalationEvent:
    """升级事件（发到事件总线，spec §6.6，emit 后不可变）。"""

    event_type: str = "error.escalation"
    level: ErrorLevel = ErrorLevel.WARN
    original_level: ErrorLevel = ErrorLevel.WARN
    message: str = ""
    component_id: str | None = None
    upgrade_path: str = ""
    timestamp: float = 0.0
    count_snapshot: dict[ErrorLevel, int] = field(default_factory=dict)


@dataclass(frozen=True)
class ErrorEscalationStats:
    """运行时可观测快照（spec §4.4 规则 2，查询返回副本）。"""

    counts: dict[ErrorLevel, int] = field(default_factory=dict)
    config: ErrorEscalationConfig = field(default_factory=ErrorEscalationConfig)
    last_event: ErrorEscalationEvent | None = None
    storm_sources: set[str] = field(default_factory=set)
    once_fired_count: int = 0


class _CrashDumpLimiter:
    """CRASH_DUMP 独立限流器（1 分钟最多 3 次，spec §5.5.1 规则 4）。

    与 StormTracker 分离：风暴抑制管 LOG/NOTIFY，快照限流管磁盘 I/O。
    """

    def __init__(
        self,
        *,
        window_sec: float = _CRASH_DUMP_WINDOW_SEC,
        max_exports: int = _CRASH_DUMP_MAX_EXPORTS,
        time_func: Callable[[], float] = time.time,
    ) -> None:
        self._window_sec = window_sec
        self._max_exports = max_exports
        self._time_func = time_func
        self._exports: list[float] = []

    def allow(self) -> bool:
        """窗口内未超限则允许并记录，否则抑制。"""
        now = self._time_func()
        self._exports = [ts for ts in self._exports if now - ts < self._window_sec]
        if len(self._exports) >= self._max_exports:
            return False
        self._exports.append(now)
        return True


class ErrorEscalator:
    """错误升级梯核心引擎。

    - 升级判定：先开关后计数（spec §5.2.1 规则 6），双重升级可叠加
      跨多级；一次 report 仅递增最终等级计数器（规则 11，P0-2）
    - 动作分派：同步先异步后（规则 11），Port 未注入跳过动作记录告警
      不抛异常（spec §5.3.3 异常场景 1）
    - 嵌套防护：_fatal_in_progress 期间再次 FATAL 跳过重复 STOP_CORE
      （spec §4.2 规则 2，对标 oops_in_progress > 1）
    """

    def __init__(
        self,
        config: ErrorEscalationConfig | None = None,
        *,
        time_func: Callable[[], float] | None = None,
        counter: ErrorCounter | None = None,
        storm: StormTracker | None = None,
    ) -> None:
        self._config = config or ErrorEscalationConfig()
        if time_func is None:
            time_func = time.time
        self._time_func = time_func
        self._counter = counter or ErrorCounter(self._config, time_func=time_func)
        self._storm = storm or StormTracker(self._config, time_func=time_func)
        self._crash_dump_limiter = _CrashDumpLimiter(time_func=time_func)
        self._fatal_in_progress = False
        self._last_event: ErrorEscalationEvent | None = None

        # 各 Port 注入（适配器层组装时注入，未注入跳过对应动作）
        self._taint_mask_port: Any = None
        self._state_machine_port: Any = None
        self._service_manager_port: Any = None
        self._event_bus_port: Any = None
        self._crash_dump_port: Any = None
        self._rate_limiter_port: Any = None
        self._control_message_port: Any = None

    # ── Port 注入 ────────────────────────────────────────────

    def set_taint_mask_port(self, port: Any) -> None:
        """注入 ZG-7 TaintedMaskPort（TAINT 动作）。"""
        self._taint_mask_port = port

    def set_state_machine_port(self, port: Any) -> None:
        """注入 ZG-6 状态机 Port（DEGRADE / STOP_CORE 动作）。"""
        self._state_machine_port = port

    def set_service_manager_port(self, port: Any) -> None:
        """注入 ZG-1 ServiceManagerPort（REPORT_FAULT / RESTART_COMPONENT）。"""
        self._service_manager_port = port

    def set_event_bus_port(self, port: Any) -> None:
        """注入 ZG-4 AutonomyEventBusPort（NOTIFY 事件）。"""
        self._event_bus_port = port

    def set_crash_dump_port(self, port: Any) -> None:
        """注入 CrashDumpPort（CRASH_DUMP 主动快照）。"""
        self._crash_dump_port = port

    def set_rate_limiter_port(self, port: Any) -> None:
        """注入 RateLimiterPort（CRITICAL/FATAL 突破日志抑制，P1-5）。"""
        self._rate_limiter_port = port

    def set_control_message_port(self, port: Any) -> None:
        """注入 ZG-8 ControlMessagePort（FATAL 级扩散取消信号，design §2.2.2.2）。"""
        self._control_message_port = port

    # ── 对外接口 ──────────────────────────────────────────────

    def report(
        self,
        level: ErrorLevel | None,
        message: str,
        *,
        component_id: str | None = None,
        exception: Exception | None = None,
        taint_flag: TaintFlag | None = None,
        once: bool = False,
    ) -> None:
        """统一错误上报入口（对标 Linux __warn / oops_enter / panic）。

        同步完成升级判定 + 同步动作 + 异步动作派发，不 await 任何异步动作。
        """
        request = ErrorReport(
            level=level,
            message=message,
            component_id=component_id,
            exception=exception,
            taint_flag=taint_flag,
            once=once,
        )
        final_level, original_level, upgrade_path = self._decide_level(request)

        # 风暴抑制决策（LOG/NOTIFY 抑制，COUNT 全量——spec §5.4.1 规则 5）
        fingerprint = self._fingerprint(component_id, message)
        decision = self._storm.check(fingerprint, once, final_level)

        # 事件快照（各等级计数）
        count_snapshot = self._counter.get_all_counts()

        # 同步动作（spec §5.3.1 规则 11：先执行，≤50μs）
        self._execute_log(level=final_level, original_level=original_level, message=message, exception=exception, decision=decision)
        self._execute_taint(level=final_level, taint_flag=taint_flag, decision=decision)

        # 异步动作（create_task 派发，不阻塞）
        actions = self._config.actions_for(final_level)
        if ErrorAction.CRASH_DUMP in actions and final_level >= self._config.crash_dump_min_level:
            self._dispatch_crash_dump(final_level, message, component_id, upgrade_path, count_snapshot)
        if ErrorAction.DEGRADE in actions:
            self._dispatch_degrade()
        if ErrorAction.REPORT_FAULT in actions and component_id is not None:
            self._dispatch_report_fault(component_id, message, exception)
        if ErrorAction.RESTART_COMPONENT in actions and component_id is not None:
            self._dispatch_restart(component_id)
        if ErrorAction.STOP_CORE in actions and final_level is ErrorLevel.FATAL:
            self._dispatch_stop_core()
        if ErrorAction.NOTIFY in actions and final_level in (ErrorLevel.CRITICAL, ErrorLevel.FATAL) and decision.log_allowed:
            self._emit_event(
                final_level=final_level,
                original_level=original_level,
                message=message,
                component_id=component_id,
                upgrade_path=upgrade_path,
                count_snapshot=count_snapshot,
                decision=decision,
            )

        # 升级路径结构化日志（spec §4.4 规则 1）
        if upgrade_path:
            logger.info(
                "ERROR_ESCALATED: original=%s final=%s path=%s counts=%s",
                original_level.value,
                final_level.value,
                upgrade_path,
                count_snapshot,
            )

    def report_warn(self, count: int, mask_matched: bool = False) -> None:
        """ZG-7 warn_count 委托入口（spec §5.9.1）。

        warn_count 权威源在 ZG-7（spec §4.2 规则 3），此处仅执行
        升级动作不重复计数；mask_matched=True 时跳过 DEGRADE
        （对标现有 mask_matched 跳过逻辑，spec §5.9.1 规则 3）。
        """
        logger.warning("ERROR_WARN_DELEGATED: count=%s mask_matched=%s", count, mask_matched)
        if not mask_matched:
            self._dispatch_degrade()

    def get_stats(self) -> ErrorEscalationStats:
        """查询当前各等级计数 + 配置开关状态 + 最近升级事件（spec §4.4 规则 2）。"""
        return ErrorEscalationStats(
            counts=self._counter.get_all_counts(),
            config=self._config,
            last_event=self._last_event,
            storm_sources=self._storm.get_storm_sources(),
            once_fired_count=self._storm.get_once_fired_count(),
        )

    def update_config(self, config: ErrorEscalationConfig, *, source: str = "runtime") -> None:
        """运行时热更新配置（对标 sysctl，立即生效不重启，spec §5.8.1 规则 3）。

        审计日志记录变更前后值（spec §5.8.1 规则 5）；仅影响后续
        report，不追溯历史（spec §5.8.3 异常场景 2）。
        """
        old = self._config
        self._config = config
        self._counter.update_config(config)
        self._storm.update_config(config)
        logger.warning(
            "ERROR_CONFIG_UPDATED: source=%s old={error_on_warn=%s,warn_error_threshold=%s,"
            "critical_on_error=%s,error_critical_threshold=%s,critical_fatal_threshold=%s,"
            "count_window_sec=%s,crash_dump_min_level=%s,storm_min_threshold=%s} "
            "new={error_on_warn=%s,warn_error_threshold=%s,critical_on_error=%s,"
            "error_critical_threshold=%s,critical_fatal_threshold=%s,count_window_sec=%s,"
            "crash_dump_min_level=%s,storm_min_threshold=%s}",
            source,
            old.error_on_warn,
            old.warn_error_threshold,
            old.critical_on_error,
            old.error_critical_threshold,
            old.critical_fatal_threshold,
            old.count_window_sec,
            old.crash_dump_min_level.value,
            old.storm_min_threshold,
            config.error_on_warn,
            config.warn_error_threshold,
            config.critical_on_error,
            config.error_critical_threshold,
            config.critical_fatal_threshold,
            config.count_window_sec,
            config.crash_dump_min_level.value,
            config.storm_min_threshold,
        )

    # ── 升级判定（spec §5.2.1）───────────────────────────────

    def _decide_level(self, request: ErrorReport) -> tuple[ErrorLevel, ErrorLevel, str]:
        """开关升级→计数升级双重驱动（design §2.1.3.1）。

        Returns:
            (final_level, original_level, upgrade_path)
        """
        original = self._normalize_level(request.level)
        final = original
        path_parts: list[str] = []

        # 开关升级（零计数成本，先应用——规则 6）
        if final is ErrorLevel.WARN and self._config.error_on_warn:
            final = ErrorLevel.ERROR
            path_parts.append("warn→error(switch)")
        if final is ErrorLevel.ERROR and self._config.critical_on_error:
            final = ErrorLevel.CRITICAL
            path_parts.append("error→critical(switch)")

        # 计数升级（check 不递增——规则 11，P0-2）
        upgraded = self._counter.check_threshold(final)
        if upgraded is not None:
            path_parts.append(f"{final.value}→{upgraded.value}(count)")
            final = upgraded
        # CRITICAL 累计达阈 → FATAL（critical_fatal_threshold）
        if final is ErrorLevel.CRITICAL and self._config.critical_fatal_threshold > 0:
            upgraded2 = self._counter.check_threshold(final)
            if upgraded2 is not None:
                path_parts.append("critical→fatal(count)")
                final = upgraded2

        # 仅递增最终等级计数器（规则 11）
        self._counter.increment(final)
        return final, original, "→".join(path_parts)

    def _normalize_level(self, level: ErrorLevel | None) -> ErrorLevel:
        """等级缺失/非法按 WARN 兜底 + 审计日志（spec §5.1.3 异常场景 2）。"""
        if level is None:
            return ErrorLevel.WARN
        if not isinstance(level, ErrorLevel):
            logger.warning("ERROR_REPORT_BAD_LEVEL: level=%r 非 ErrorLevel，按 WARN 兜底", level)
            return ErrorLevel.WARN
        return level

    # ── 同步动作 ─────────────────────────────────────────────

    def _execute_log(
        self,
        *,
        level: ErrorLevel,
        original_level: ErrorLevel,
        message: str,
        exception: Exception | None,
        decision: StormDecision,
    ) -> None:
        """LOG 动作（同步）。抑制时静默；CRITICAL/FATAL 前调
        RateLimiterPort.set_min_level 突破抑制（P1-5 Suppressor 联动）。"""
        if not decision.log_allowed:
            return
        # P1-5：CRITICAL/FATAL 级突破日志抑制（对标 console_verbose）
        if level in (ErrorLevel.CRITICAL, ErrorLevel.FATAL) and self._rate_limiter_port is not None:
            try:
                self._rate_limiter_port.set_min_level(_LEVEL_CRITICAL)
            except Exception as exc:
                logger.warning("ERROR_RATE_LIMITER_FAILED: %s", exc)
        log_level = _LOG_LEVELS[level]
        logger.log(
            log_level,
            "ERROR_REPORT: level=%s original=%s message=%s%s",
            level.value,
            original_level.value,
            message,
            "" if exception is None else f" exception={exception!r}",
        )

    def _execute_taint(self, *, level: ErrorLevel, taint_flag: TaintFlag | None, decision: StormDecision) -> None:
        """TAINT 动作（同步，幂等置位）。

        ONCE 抑制：once=True 首次完整响应含 TAINT，后续静默
        （spec §5.4.1 规则 1 验收：仅第 1 次执行 LOG/TAINT）。
        """
        if not decision.log_allowed:
            return
        actions = self._config.actions_for(level)
        if ErrorAction.TAINT not in actions:
            return
        flag = taint_flag or _DEFAULT_TAINT_FLAGS.get(level)
        if flag is None:
            # CRITICAL/FATAL 默认动作集不含 TAINT（现有 8 位 TaintFlag
            # 无对应标志位，spec §5.3.1 规则 3）；显式指定 taint_flag
            # 时仍可写入
            return
        if self._taint_mask_port is None:
            logger.warning("ERROR_PORT_MISSING: taint_mask_port 未注入，跳过 TAINT")
            return
        try:
            self._taint_mask_port.add_taint(flag)
        except Exception as exc:
            logger.warning("ERROR_TAINT_FAILED: %s", exc)

    # ── 异步动作（create_task 派发，不阻塞）─────────────────

    def _dispatch(self, description: str, coro_factory: Callable[[], Any], on_done: Callable[[], None] | None = None) -> None:
        """create_task 派发 + done callback 异常捕获（spec §5.3.3 异常场景 2）。

        Args:
            description: 动作描述（审计日志）
            coro_factory: 协程工厂（返回待调度协程）
            on_done: 任务完成回调（如嵌套防护标志重置）

        Raises:
            TypeError: coro_factory 返回非协程（如误传同步方法）——调用方
                负责保证工厂返回协程；本方法对 create_task 自身异常兜底
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning("ERROR_NO_LOOP: 无运行中事件循环，跳过异步动作 %s", description)
            return
        try:
            task = loop.create_task(coro_factory())
        except Exception as exc:
            # create_task 兜底（spec §5.3.3 异常场景 2）：非协程/循环关闭等
            # 不阻断 report 主流程（CX 审查 P1 修复——原实现未包 try）
            logger.warning("ERROR_ACTION_DISPATCH_FAILED: %s: %s", description, exc)
            return

        def _on_done(t: asyncio.Task) -> None:
            if on_done is not None:
                on_done()
            if t.cancelled():
                return
            exc = t.exception()
            if exc is not None:
                logger.warning("ERROR_ACTION_FAILED: %s: %s", description, exc)

        task.add_done_callback(_on_done)

    def _dispatch_degrade(self) -> None:
        """DEGRADE：异步驱动 ZG-6 进入 DEGRADING（design §2.1.3.6）。

        BOOTING/SHUTTING_DOWN 期间由状态机自行忽略（state_machine.py:113）。
        """
        if self._state_machine_port is None:
            logger.warning("ERROR_PORT_MISSING: state_machine_port 未注入，跳过 DEGRADE")
            return

        def _factory() -> Any:
            return self._state_machine_port.trigger_health_level_change(SystemHealthLevel.DEGRADED)

        self._dispatch("DEGRADE", _factory)

    def _dispatch_report_fault(self, component_id: str, message: str, exception: Exception | None) -> None:
        """REPORT_FAULT：异步上报组件故障（需 component_id，spec §5.1.1 规则 4）。"""
        if self._service_manager_port is None:
            logger.warning("ERROR_PORT_MISSING: service_manager_port 未注入，跳过 REPORT_FAULT")
            return

        def _factory() -> Any:
            detail = message if exception is None else f"{message}: {exception}"
            return self._service_manager_port.report_external_fault(component_id, "error_escalation", detail)

        self._dispatch("REPORT_FAULT", _factory)

    def _dispatch_restart(self, component_id: str) -> None:
        """RESTART_COMPONENT：异步重启故障组件（需 component_id）。"""
        if self._service_manager_port is None:
            logger.warning("ERROR_PORT_MISSING: service_manager_port 未注入，跳过 RESTART_COMPONENT")
            return

        def _factory() -> Any:
            return self._service_manager_port.restart(component_id)

        self._dispatch("RESTART_COMPONENT", _factory)

    def _dispatch_stop_core(self) -> None:
        """STOP_CORE：异步驱动 ZG-6 优雅停机（不杀进程，N2 裁决）。

        嵌套防护（spec §4.2 规则 2）：_fatal_in_progress 期间再次
        FATAL 跳过重复 STOP_CORE（对标 oops_in_progress > 1）。
        """
        if self._state_machine_port is None:
            logger.warning("ERROR_PORT_MISSING: state_machine_port 未注入，跳过 STOP_CORE")
            return
        if self._fatal_in_progress:
            logger.warning("ERROR_FATAL_NESTED: STOP_CORE 已在进行中，跳过重复停机")
            return
        self._fatal_in_progress = True

        # FATAL 级扩散取消信号（design §1.2.5，对标 zap_other_threads）：
        # 投递系统级引擎致命控制消息（force_send 绕过屏蔽），由控制消息
        # 处理链触发 FatalDiffuser 扩散取消在途会话任务；Port 未注入跳过
        if self._control_message_port is not None:

            def _diffuse_factory() -> Any:
                return self._control_message_port.force_send(
                    ControlMessageKind.ENGINE_FATAL_ERROR,
                    reason="error-escalation-stop-core",
                    caller="error_escalation",
                )

            self._dispatch("FATAL_DIFFUSE", _diffuse_factory)

        def _factory() -> Any:
            return self._state_machine_port.trigger_shutdown()

        # 完成后置 False（design §2.1.3.1 嵌套防护设计）：执行期间再次
        # FATAL 跳过重复停机；任务完成后允许重试
        def _reset() -> None:
            self._fatal_in_progress = False

        self._dispatch("STOP_CORE", _factory, on_done=_reset)

    def _dispatch_crash_dump(
        self,
        level: ErrorLevel,
        message: str,
        component_id: str | None,
        upgrade_path: str,
        count_snapshot: dict[ErrorLevel, int],
    ) -> None:
        """CRASH_DUMP：半异步主动快照（独立限流 1 分钟 3 次，spec §5.5.1 规则 4）。

        export_snapshot 本身是同步方法（CrashDumpPort 同步签名，design
        §2.1.3.2 "半异步"），**直接同步调用**——之前误入 create_task 派发
        导致生产注入同步 CrashDump 时抛 TypeError（CX 审查 P1 发现）。
        IOError 等失败在 export_snapshot 内捕获，不阻塞其他动作
        （spec §5.5.1 规则 5）；只读导出不修改全局状态（规则 6）。
        """
        if self._crash_dump_port is None:
            logger.warning("ERROR_PORT_MISSING: crash_dump_port 未注入，跳过 CRASH_DUMP")
            return
        if not self._crash_dump_limiter.allow():
            logger.debug("ERROR_CRASH_DUMP_SKIPPED: 1 分钟内快照次数超限，静默")
            return
        try:
            context = {
                "level": level.value,
                "message": message,
                "component_id": component_id,
                "upgrade_path": upgrade_path,
                "counts": count_snapshot,
            }
            self._crash_dump_port.export_snapshot(f"error-escalation-{level.value}", context)
        except Exception as exc:
            # 同步导出失败不阻断 report 主流程（spec §5.5.1 规则 5）
            logger.warning("ERROR_CRASH_DUMP_FAILED: %s", exc)

    def _emit_event(
        self,
        *,
        final_level: ErrorLevel,
        original_level: ErrorLevel,
        message: str,
        component_id: str | None,
        upgrade_path: str,
        count_snapshot: dict[ErrorLevel, int],
        decision: StormDecision,
    ) -> None:
        """NOTIFY：事件总线发 error.escalation（emit_sync，design §2.2.2.2）。"""
        event = ErrorEscalationEvent(
            level=final_level,
            original_level=original_level,
            message=message,
            component_id=component_id,
            upgrade_path=upgrade_path,
            timestamp=self._time_func(),
            count_snapshot=count_snapshot,
        )
        self._last_event = event
        if self._event_bus_port is None:
            logger.warning("ERROR_PORT_MISSING: event_bus_port 未注入，跳过 NOTIFY")
            return
        try:
            self._event_bus_port.emit_sync("error.escalation", event.__dict__)
        except Exception as exc:
            logger.warning("ERROR_NOTIFY_FAILED: %s", exc)

    # ── 工具 ────────────────────────────────────────────────

    @staticmethod
    def _fingerprint(component_id: str | None, message: str) -> str:
        """源指纹 = component_id + message 哈希（spec §5.4.1 规则 1）。"""
        raw = f"{component_id or ''}|{message}"  # component_id or '': None 豁免（外部传入可能 None）
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
