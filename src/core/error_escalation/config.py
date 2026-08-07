"""错误升级梯 — 升级配置（ZG-14）。

ErrorEscalationConfig frozen dataclass：9 配置项，对标 Linux
panic_on_warn / warn_limit / panic_on_oops 参数。校验失败回退全默认
（spec §5.8.1 规则 4），禁止配置项支持杀进程语义（N2 裁决）。
"""

from dataclasses import dataclass

from src.core.error_escalation.types import ErrorAction, ErrorLevel

# 阈值非法时回退的默认值
_DEFAULT_ERROR_ON_WARN = False
_DEFAULT_WARN_ERROR_THRESHOLD = 0
_DEFAULT_CRITICAL_ON_ERROR = False
_DEFAULT_ERROR_CRITICAL_THRESHOLD = 0
_DEFAULT_CRITICAL_FATAL_THRESHOLD = 0
_DEFAULT_LEVEL_ACTIONS = None
_DEFAULT_COUNT_WINDOW_SEC = 0.0
_DEFAULT_CRASH_DUMP_MIN_LEVEL = ErrorLevel.CRITICAL
_DEFAULT_STORM_MIN_THRESHOLD = 100


DEFAULT_LEVEL_ACTIONS: dict[ErrorLevel, tuple[ErrorAction, ...]] = {
    # 对标 Linux WARN_ON：记日志 + warn_count++ + taint
    ErrorLevel.WARN: (
        ErrorAction.LOG,
        ErrorAction.TAINT,
        ErrorAction.COUNT,
    ),
    # 对标 oops：dump + 降级 + 标记 FAULT
    ErrorLevel.ERROR: (
        ErrorAction.LOG,
        ErrorAction.TAINT,
        ErrorAction.COUNT,
        ErrorAction.DEGRADE,
        ErrorAction.REPORT_FAULT,
    ),
    # 对标 panic：kmsg_dump + 重启 + 通知
    ErrorLevel.CRITICAL: (
        ErrorAction.LOG,
        ErrorAction.CRASH_DUMP,
        ErrorAction.RESTART_COMPONENT,
        ErrorAction.NOTIFY,
    ),
    # 对标 panic + panic_timeout：停机 + 转储 + 通知（不杀进程）
    ErrorLevel.FATAL: (
        ErrorAction.LOG,
        ErrorAction.CRASH_DUMP,
        ErrorAction.STOP_CORE,
        ErrorAction.NOTIFY,
    ),
}


@dataclass(frozen=True)
class ErrorEscalationConfig:
    """错误升级配置（不可变，运行时热更新通过整实例原子替换）。

    spec §6.3：默认所有升级开关关闭、所有阈值=0（禁用计数升级）、
    level_actions=None（用默认动作集）、count_window_sec=0（全局累计）、
    crash_dump_min_level=CRITICAL、storm_min_threshold=100。
    """

    error_on_warn: bool = _DEFAULT_ERROR_ON_WARN
    """True 时 WARN 升级 ERROR（对标 panic_on_warn）。"""
    warn_error_threshold: int = _DEFAULT_WARN_ERROR_THRESHOLD
    """WARN 累计达阈升级 ERROR（0=禁用）。"""
    critical_on_error: bool = _DEFAULT_CRITICAL_ON_ERROR
    """True 时 ERROR 升级 CRITICAL（对标 panic_on_oops）。"""
    error_critical_threshold: int = _DEFAULT_ERROR_CRITICAL_THRESHOLD
    """ERROR 累计达阈升级 CRITICAL（0=禁用）。"""
    critical_fatal_threshold: int = _DEFAULT_CRITICAL_FATAL_THRESHOLD
    """CRITICAL 累计达阈升级 FATAL（0=禁用）。"""
    level_actions: dict[ErrorLevel, list[ErrorAction]] | None = _DEFAULT_LEVEL_ACTIONS
    """按等级覆盖默认动作集（None=用 DEFAULT_LEVEL_ACTIONS，未覆盖的等级用默认）。"""
    count_window_sec: float = _DEFAULT_COUNT_WINDOW_SEC
    """计数窗口（秒，0=全局累计不归零，>0 按窗口归零）。"""
    crash_dump_min_level: ErrorLevel = _DEFAULT_CRASH_DUMP_MIN_LEVEL
    """仅该级及以上触发 CRASH_DUMP 动作。"""
    storm_min_threshold: int = _DEFAULT_STORM_MIN_THRESHOLD
    """风暴检测独立下限阈值（计数阈值=0 时风暴检测仍用此值，P2-3 修复）。"""

    def actions_for(self, level: ErrorLevel) -> tuple[ErrorAction, ...]:
        """取指定等级动作集（level_actions 覆盖默认，未覆盖的等级用默认）。"""
        if self.level_actions is not None:
            override = self.level_actions.get(level)
            if override is not None:
                return tuple(override)
        return DEFAULT_LEVEL_ACTIONS[level]


def _parse_bool(value: object, name: str, issues: list[str]) -> bool:
    """解析布尔配置，失败回退默认并记录告警；字段缺失（None）静默用默认。"""
    if value is None or isinstance(value, bool):
        return _DEFAULT_ERROR_ON_WARN if value is None else value
    try:
        return str(value).strip().lower() in ("true", "1", "yes", "on")
    except Exception as exc:
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port
        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.WARNING, "解析 error_escalation 布尔配置失败，回退默认 False", exception=exc)
        issues.append(f"error_escalation.{name} 解析失败，回退默认 False")
        return _DEFAULT_ERROR_ON_WARN


def _parse_threshold(value: object, name: str, issues: list[str]) -> int:
    """解析计数阈值（≥0），负数/非数字回退默认并记录告警（spec §5.2.3 异常场景 2）；
    字段缺失（None）静默用默认（0=禁用）。"""
    if value is None:
        return _DEFAULT_WARN_ERROR_THRESHOLD
    try:
        parsed = int(value)  # type: ignore[arg-type]
        if parsed < 0:
            issues.append(f"error_escalation.{name}={value} 为负数，按 0 处理（禁用该级计数升级）")
            return 0
        return parsed
    except (TypeError, ValueError):
        issues.append(f"error_escalation.{name}={value} 解析失败，回退默认 0")
        return _DEFAULT_WARN_ERROR_THRESHOLD


def _parse_level(value: object, issues: list[str]) -> ErrorLevel:
    """解析错误等级，非法回退 CRITICAL 并记录告警；字段缺失（None）静默用默认。"""
    if value is None:
        return _DEFAULT_CRASH_DUMP_MIN_LEVEL
    if isinstance(value, ErrorLevel):
        return value
    try:
        return ErrorLevel(str(value).strip().lower())
    except (ValueError, AttributeError):
        issues.append(f"error_escalation.crash_dump_min_level={value} 非法，回退默认 CRITICAL")
        return _DEFAULT_CRASH_DUMP_MIN_LEVEL


def _parse_level_actions(value: object, issues: list[str]) -> dict[ErrorLevel, list[ErrorAction]] | None:
    """解析动作集覆盖表，任一非法动作整项回退 None（spec §5.8.1 规则 4）。"""
    if value is None:
        return None
    if not isinstance(value, dict):
        issues.append("error_escalation.level_actions 非 dict，回退默认动作集")
        return None
    parsed: dict[ErrorLevel, list[ErrorAction]] = {}
    for raw_level, raw_actions in value.items():
        try:
            level = raw_level if isinstance(raw_level, ErrorLevel) else ErrorLevel(str(raw_level).strip().lower())
        except (ValueError, AttributeError):
            issues.append(f"error_escalation.level_actions 键 {raw_level} 非法，level_actions 整体回退默认")
            return None
        if not isinstance(raw_actions, (list, tuple)):
            issues.append(f"error_escalation.level_actions[{raw_level}] 非列表，level_actions 整体回退默认")
            return None
        actions: list[ErrorAction] = []
        for raw_action in raw_actions:
            try:
                action = raw_action if isinstance(raw_action, ErrorAction) else ErrorAction(str(raw_action).strip().lower())
            except (ValueError, AttributeError):
                issues.append(
                    f"error_escalation.level_actions[{raw_level}] 含非法动作 {raw_action}，level_actions 整体回退默认"
                )
                return None
            actions.append(action)
        parsed[level] = actions
    return parsed


def build_config(mapping: dict[str, object] | None = None) -> tuple[ErrorEscalationConfig, list[str]]:
    """从配置字典构造 ErrorEscalationConfig。

    校验失败回退全默认并返回告警列表（spec §5.8.1 规则 4）；映射为 None
    （配置文件缺失/字段缺失）时按全默认加载并返回缺失告警
    （spec §5.8.3 异常场景 1）。

    Args:
        mapping: 配置字典（键与配置项同名，字符串形式可含 JSON 来源的值）

    Returns:
        (config, issues)：issues 为告警列表（空=全部合法）
    """
    issues: list[str] = []
    if mapping is None:
        issues.append("error_escalation 配置缺失，按全默认加载")
        return ErrorEscalationConfig(), issues

    error_on_warn = _parse_bool(mapping.get("error_on_warn"), "error_on_warn", issues)
    critical_on_error = _parse_bool(mapping.get("critical_on_error"), "critical_on_error", issues)

    warn_error_threshold = _parse_threshold(mapping.get("warn_error_threshold"), "warn_error_threshold", issues)
    error_critical_threshold = _parse_threshold(mapping.get("error_critical_threshold"), "error_critical_threshold", issues)
    critical_fatal_threshold = _parse_threshold(mapping.get("critical_fatal_threshold"), "critical_fatal_threshold", issues)

    level_actions = _parse_level_actions(mapping.get("level_actions"), issues)
    count_window_sec = _parse_window(mapping.get("count_window_sec"), issues)
    crash_dump_min_level = _parse_level(mapping.get("crash_dump_min_level"), issues)
    storm_min_threshold = _parse_storm_min(mapping.get("storm_min_threshold"), issues)

    return ErrorEscalationConfig(
        error_on_warn=error_on_warn,
        warn_error_threshold=warn_error_threshold,
        critical_on_error=critical_on_error,
        error_critical_threshold=error_critical_threshold,
        critical_fatal_threshold=critical_fatal_threshold,
        level_actions=level_actions,
        count_window_sec=count_window_sec,
        crash_dump_min_level=crash_dump_min_level,
        storm_min_threshold=storm_min_threshold,
    ), issues


def _parse_window(value: object, issues: list[str]) -> float:
    """解析计数窗口（≥0），负数/非数字回退默认并记录告警；字段缺失静默用默认。"""
    if value is None:
        return _DEFAULT_COUNT_WINDOW_SEC
    try:
        parsed = float(value)  # type: ignore[arg-type]
        if parsed < 0:
            issues.append(f"error_escalation.count_window_sec={value} 为负数，按 0 处理（全局累计）")
            return 0.0
        return parsed
    except (TypeError, ValueError):
        issues.append(f"error_escalation.count_window_sec={value} 解析失败，回退默认 0")
        return _DEFAULT_COUNT_WINDOW_SEC


def _parse_storm_min(value: object, issues: list[str]) -> int:
    """解析风暴检测下限阈值（≥1），非法回退默认并记录告警；字段缺失静默用默认。"""
    if value is None:
        return _DEFAULT_STORM_MIN_THRESHOLD
    try:
        parsed = int(value)  # type: ignore[arg-type]
        if parsed < 1:
            issues.append(f"error_escalation.storm_min_threshold={value} 非法，回退默认 {_DEFAULT_STORM_MIN_THRESHOLD}")
            return _DEFAULT_STORM_MIN_THRESHOLD
        return parsed
    except (TypeError, ValueError):
        issues.append(f"error_escalation.storm_min_threshold={value} 解析失败，回退默认 {_DEFAULT_STORM_MIN_THRESHOLD}")
        return _DEFAULT_STORM_MIN_THRESHOLD
