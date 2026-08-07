"""错误升级梯 — 等级与动作枚举（ZG-14）。

对标 Linux bug_trap_type + panic_on_* 参数：
- ErrorLevel: WARN→ERROR→CRITICAL→FATAL 单向递进，对标 WARN→oops→panic
- ErrorAction: 响应动作集，禁止 panic/kill/exit 杀进程语义（N2 裁决）
"""

from enum import Enum


class ErrorLevel(str, Enum):
    """错误等级（四级，自低到高，语义不可变）。

    对标 Linux bug_trap_type。追加只能更高位（如未来加 EMERG 必须在
    FATAL 之上），禁止插中间（spec §6.1 规则 2）。
    """

    WARN = "warn"  # 记日志 + 计数 + taint，继续运行
    WARNING = "warn"  # 别名：对齐 Python logging.WARN/WARNING 并存先例（ZG-14 Phase 4 模板误用 WARNING，统一别名兼容）
    ERROR = "error"  # 降级运行 + 发事件 + 标记组件 FAULT
    CRITICAL = "critical"  # crash_dump 快照 + 重启组件
    FATAL = "fatal"  # 停核心 + 转储 + 通知（不杀进程，N2 裁决）

    def __lt__(self, other: object) -> bool:
        """序比较（WARN < ERROR < CRITICAL < FATAL），供级别判定使用。"""
        if not isinstance(other, ErrorLevel):
            return NotImplemented
        return _LEVEL_ORDER[self] < _LEVEL_ORDER[other]

    def __le__(self, other: object) -> bool:
        if not isinstance(other, ErrorLevel):
            return NotImplemented
        return _LEVEL_ORDER[self] <= _LEVEL_ORDER[other]

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, ErrorLevel):
            return NotImplemented
        return _LEVEL_ORDER[self] > _LEVEL_ORDER[other]

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, ErrorLevel):
            return NotImplemented
        return _LEVEL_ORDER[self] >= _LEVEL_ORDER[other]


# 等级顺序映射（成员定义序，追加只能更高位不插中间）
_LEVEL_ORDER = {level: index for index, level in enumerate(ErrorLevel)}


class ErrorAction(str, Enum):
    """错误响应动作（九种，对标 Linux panic_on_* 可配置动作集）。

    禁止包含 "panic" / "kill" / "exit" 等杀进程语义动作（spec §6.2 规则 3）。
    """

    LOG = "log"  # 经 ZG-2 logger 记日志（WARN→WARNING / ERROR→ERROR / CRITICAL→CRITICAL / FATAL→CRITICAL）
    TAINT = "taint"  # 经 ZG-7 写污染标志（WARN→TAINT_WARN / ERROR→TAINT_EXCEPTION_SWALLOWED）
    COUNT = "count"  # 递增对应等级计数器（标记项：计数是升级判定的内在行为，不受配置影响）
    DEGRADE = "degrade"  # 异步驱动 ZG-6 进入 DEGRADING
    REPORT_FAULT = "report_fault"  # 异步调 ZG-1 上报组件故障（需 component_id）
    CRASH_DUMP = "crash_dump"  # 主动导出崩溃快照（不等进程死）
    RESTART_COMPONENT = "restart_component"  # 异步调 ZG-1 重启故障组件（需 component_id）
    STOP_CORE = "stop_core"  # 异步驱动 ZG-6 优雅停机（停接新请求，不杀进程）
    NOTIFY = "notify"  # 经事件总线发 error.escalation 事件（仅 CRITICAL/FATAL）
