"""ZG-6 系统生命周期状态机 — 类型定义。

对标 Linux enum system_states（include/linux/kernel.h:180）。
顺序不可变：迁移表用 <, >= 偏序守卫（"Ordering must not be changed"）。
"""

from dataclasses import dataclass
from enum import Enum, IntEnum


class SystemLifecycleState(IntEnum):
    """系统生命周期状态 — 有序枚举，偏序守卫。"""

    BOOTING = 0
    READY = 1
    DEGRADING = 2
    SHUTTING_DOWN = 3

    @property
    def snake_case(self) -> str:
        return self.name.lower()

    def is_booting(self) -> bool:
        return self is SystemLifecycleState.BOOTING

    def is_ready(self) -> bool:
        return self is SystemLifecycleState.READY

    def is_degrading(self) -> bool:
        return self is SystemLifecycleState.DEGRADING

    def is_shutting_down(self) -> bool:
        return self is SystemLifecycleState.SHUTTING_DOWN

    def is_running_like(self) -> bool:
        """READY 或 DEGRADING — 仍在运行，对标 system_state < SYSTEM_HALT。"""
        return self in (SystemLifecycleState.READY, SystemLifecycleState.DEGRADING)


class TransitionReason(str, Enum):
    """状态迁移原因。"""

    STARTUP_COMPLETE = "startup_complete"
    STARTUP_COMPLETE_DEGRADED = "startup_complete_degraded"
    HEALTH_LEVEL_CHANGE = "health_level_change"
    RECOVERY = "recovery"
    SHUTDOWN_SIGNAL = "shutdown_signal"


@dataclass(frozen=True)
class TransitionRecord:
    """单次迁移历史记录。"""

    timestamp: float
    old_state: SystemLifecycleState
    new_state: SystemLifecycleState
    reason: TransitionReason
    duration_ms: float


@dataclass
class SystemLifecycleView:
    """WebUI 内省视图。"""

    state: SystemLifecycleState
    health_level: str
    core_readiness: tuple[bool, bool, bool]
    transition_history: list[TransitionRecord]
    generated_at: float


class IllegalTransitionError(Exception):
    """非法状态迁移。"""
