"""错误升级梯 — 适配器层（ZG-14）。

ErrorEscalationAdapter 实现 ErrorEscalationPort，组装 ErrorEscalator
并注入各 Port（TaintedMaskPort / SystemStateMachinePort /
ServiceManagerPort / AutonomyEventBusPort / CrashDumpPort /
RateLimiterPort / AppConfigPort）。

适配器层是唯一允许导入 ZG-14 具体类的位置（核心禁止项 13）：
核心模块仅依赖 Protocol 接口，具体实现由 main.py 启动时注入。
"""

import time
from typing import Any, Callable

from src.common.logger import get_logger
from src.core.error_escalation.config import ErrorEscalationConfig, build_config
from src.core.error_escalation.escalator import ErrorEscalationStats, ErrorEscalator
from src.core.error_escalation.types import ErrorLevel

logger = get_logger("error_escalation.adapter")


def _load_config_from_port(app_config_port: Any) -> ErrorEscalationConfig:
    """从 AppConfigPort 加载 error_escalation 配置域。

    get_error_escalation_config() 在 Phase 3（配置模板落地）后提供；
    缺失时按全默认加载并记录告警（spec §5.8.3 异常场景 1）。
    """
    if app_config_port is None:
        return ErrorEscalationConfig()
    try:
        raw = app_config_port.get_error_escalation_config()
    except AttributeError:
        logger.warning("ERROR_CONFIG_SOURCE_MISSING: AppConfigPort 无 error_escalation 配置域，按全默认加载")
        return ErrorEscalationConfig()
    except Exception as exc:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.WARNING, "加载错误升级配置失败，按全默认加载", exception=exc)
        logger.warning("ERROR_CONFIG_LOAD_FAILED: %s，按全默认加载", exc)
        return ErrorEscalationConfig()
    config, issues = build_config(raw if isinstance(raw, dict) else None)
    for issue in issues:
        logger.warning("ERROR_CONFIG_ISSUE: %s", issue)
    return config


class ErrorEscalationAdapter:
    """ErrorEscalationPort 适配器实现 — 组装引擎 + Port 注入。

    启动时由 main.py 创建并注册到 error_escalation_port_registry。
    """

    def __init__(
        self,
        config: ErrorEscalationConfig | None = None,
        *,
        app_config_port: Any = None,
        taint_mask_port: Any = None,
        state_machine_port: Any = None,
        service_manager_port: Any = None,
        event_bus_port: Any = None,
        crash_dump_port: Any = None,
        rate_limiter_port: Any = None,
        control_message_port: Any = None,
        time_func: Callable[[], float] = time.time,
    ) -> None:
        """初始化适配器。

        Args:
            config: 显式配置（None 时从 app_config_port 加载或全默认）
            app_config_port: AppConfigPort（配置加载，可选）
            taint_mask_port: ZG-7 TaintedMaskPort（TAINT 动作）
            state_machine_port: ZG-6 SystemStateMachinePort（DEGRADE/STOP_CORE）
            service_manager_port: ZG-1 ServiceManagerPort（REPORT_FAULT/RESTART）
            event_bus_port: ZG-4 AutonomyEventBusPort（NOTIFY 事件）
            crash_dump_port: CrashDumpPort（CRASH_DUMP 主动快照）
            rate_limiter_port: RateLimiterPort（CRITICAL/FATAL 突破抑制，P1-5）
            control_message_port: ZG-8 ControlMessagePort（FATAL 级扩散取消信号）
            time_func: 时间函数注入点（测试可替换）
        """
        if config is None:
            config = _load_config_from_port(app_config_port)
        self._escalator = ErrorEscalator(config, time_func=time_func)
        self._escalator.set_taint_mask_port(taint_mask_port)
        self._escalator.set_state_machine_port(state_machine_port)
        self._escalator.set_service_manager_port(service_manager_port)
        self._escalator.set_event_bus_port(event_bus_port)
        self._escalator.set_crash_dump_port(crash_dump_port)
        self._escalator.set_rate_limiter_port(rate_limiter_port)
        self._escalator.set_control_message_port(control_message_port)
        self._config_loaded = config

    # ── ErrorEscalationPort 实现 ─────────────────────────────

    def report(
        self,
        level: ErrorLevel,
        message: str,
        *,
        component_id: str | None = None,
        exception: Exception | None = None,
        taint_flag: Any = None,
        once: bool = False,
    ) -> None:
        """统一错误上报入口（委托核心引擎）。"""
        self._escalator.report(
            level,
            message,
            component_id=component_id,
            exception=exception,
            taint_flag=taint_flag,
            once=once,
        )

    def report_warn(self, count: int, mask_matched: bool = False) -> None:
        """ZG-7 warn_count 委托入口。"""
        self._escalator.report_warn(count, mask_matched=mask_matched)

    def get_stats(self) -> ErrorEscalationStats:
        """查询各等级计数 + 配置 + 最近事件。"""
        return self._escalator.get_stats()

    def update_config(self, config: ErrorEscalationConfig, *, source: str = "runtime") -> None:
        """运行时热更新配置（审计日志记录变更）。"""
        self._escalator.update_config(config, source=source)

    # ── 测试/运维辅助 ────────────────────────────────────────

    @property
    def escalator(self) -> ErrorEscalator:
        """内部引擎访问（仅测试与运维诊断使用）。"""
        return self._escalator
