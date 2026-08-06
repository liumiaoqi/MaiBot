"""错误升级梯（ZG-14）— 统一错误分级 + 升级梯判定 + 动作分派。

对标 Linux WARN→oops→panic 升级梯（lib/bug.c + kernel/panic.c）：
错误沿 WARN→ERROR→CRITICAL→FATAL 单向递进，由配置开关与计数阈值
双重驱动；最高动作 STOP_CORE 优雅停机，全程不杀进程（N2 裁决）。
"""

from src.core.error_escalation.adapter import ErrorEscalationAdapter
from src.core.error_escalation.config import DEFAULT_LEVEL_ACTIONS, ErrorEscalationConfig, build_config
from src.core.error_escalation.counter import ErrorCounter
from src.core.error_escalation.escalator import (
    ErrorEscalationEvent,
    ErrorEscalationStats,
    ErrorEscalator,
    ErrorReport,
)
from src.core.error_escalation.mapper import EnumLevelMapper, default_mapper
from src.core.error_escalation.storm import StormDecision, StormTracker
from src.core.error_escalation.types import ErrorAction, ErrorLevel

__all__ = [
    "DEFAULT_LEVEL_ACTIONS",
    "EnumLevelMapper",
    "ErrorAction",
    "ErrorEscalationAdapter",
    "ErrorEscalationConfig",
    "ErrorEscalationEvent",
    "ErrorEscalationStats",
    "ErrorEscalator",
    "ErrorCounter",
    "ErrorLevel",
    "ErrorReport",
    "StormDecision",
    "StormTracker",
    "build_config",
    "default_mapper",
]
