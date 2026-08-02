"""ZG-8 控制消息优先级 — 数据结构定义。

对标 Linux 内核信号机制（signal.c）：
- ControlMessageKind 对标信号编号（signal.h 信号定义）
- ControlMessage 对标 siginfo
- ControlMessagePendingNode 对标 sigqueue 队列节点
- 屏蔽位图对标 sigset_t

位图约定：类别编号 kind 对应位 (1 << (kind - 1))，位 0 对应编号 1。
"""

from dataclasses import dataclass
from enum import Enum, IntEnum
from typing import Any


class ControlMessageKind(IntEnum):
    """控制消息类别编号 — 对标 Linux 信号编号。

    六大类别按编号区间划分，低编号优先（ADR-02）：
    - 1-3 系统级强制（不可屏蔽，对标 SIGKILL/SIGSTOP）
    - 4-6 引擎致命（同步优先，对标 SYNCHRONOUS_MASK）
    - 7-9 会话控制
    - 10-11 调试追踪
    - 12-14 普通控制（标准去重，对标 legacy_queue）
    - 15-16 实时控制（同类排队，对标 SIGRTMIN+）
    """

    # 系统级强制（不可屏蔽）
    EMERGENCY_STOP = 1
    FORCE_SHUTDOWN = 2
    FORCE_OFFLINE = 3
    # 引擎致命（同步优先）
    ENGINE_FATAL_ERROR = 4
    MEMORY_SUBSYSTEM_FAILURE = 5
    SESSION_CORRUPTED = 6
    # 会话控制
    SESSION_STOP = 7
    SESSION_RESUME = 8
    SESSION_DESTROY = 9
    # 调试追踪
    DEBUG_TRACE = 10
    INSPECT_REQUEST = 11
    # 普通控制（标准去重）
    PAUSE_REPLY = 12
    RESUME_REPLY = 13
    RELOAD_CONFIG = 14
    # 实时控制（同类排队）
    URGENT_NOTICE = 15
    RATE_LIMIT_HIT = 16


class ControlMessageCategory(Enum):
    """控制消息大类。"""

    SYSTEM_FORCE = "system_force"
    ENGINE_FATAL = "engine_fatal"
    SESSION_CONTROL = "session_control"
    DEBUG_TRACE = "debug_trace"
    NORMAL = "normal"
    REALTIME = "realtime"


class MaskOperation(Enum):
    """屏蔽集操作类型 — 对标 Linux sigprocmask 的 how 参数。"""

    BLOCK = "block"
    UNBLOCK = "unblock"
    SETMASK = "setmask"


class MaskScope(Enum):
    """屏蔽集作用域。"""

    SYSTEM = "system"
    SESSION = "session"


class DeliveryResult(Enum):
    """投递结果。"""

    DELIVERED = "delivered"
    QUEUED = "queued"
    REJECTED = "rejected"
    REJECTED_BLOCKED = "rejected_blocked"
    REJECTED_IGNORED = "rejected_ignored"
    REJECTED_UNKILLABLE = "rejected_unkillable"
    FORCE_DELIVERED = "force_delivered"
    TARGET_GONE = "target_gone"


class ProtectionAction(Enum):
    """UNKILLABLE 保护判定动作。"""

    PROCEED = "proceed"
    REJECTED = "rejected"
    CLEARED = "cleared"


# ── 掩码常量（位图 = 1 << (kind - 1)）──────────────────────────────

# 引擎致命类别（编号 4-6）— 同步优先掩码，对标 Linux SYNCHRONOUS_MASK
SYNCHRONOUS_MASK = (
    (1 << (ControlMessageKind.ENGINE_FATAL_ERROR - 1))
    | (1 << (ControlMessageKind.MEMORY_SUBSYSTEM_FAILURE - 1))
    | (1 << (ControlMessageKind.SESSION_CORRUPTED - 1))
)

# 系统级强制类别（编号 1-3）— 不可屏蔽掩码，对标 Linux SIG_KERNEL_ONLY_MASK
UNMASKABLE_MASK = (
    (1 << (ControlMessageKind.EMERGENCY_STOP - 1))
    | (1 << (ControlMessageKind.FORCE_SHUTDOWN - 1))
    | (1 << (ControlMessageKind.FORCE_OFFLINE - 1))
)

# 标准控制消息（编号 1-14）— 同类去重，对标 Linux 标准信号（1-31）
STANDARD_MASK = (1 << 14) - 1

# 实时控制消息（编号 15-16）— 同类排队，对标 Linux 实时信号（32-64）
REALTIME_MASK = (
    (1 << (ControlMessageKind.URGENT_NOTICE - 1))
    | (1 << (ControlMessageKind.RATE_LIMIT_HIT - 1))
)


# ── 数据结构 ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class ControlMessage:
    """控制消息体 — 对标 Linux siginfo。"""

    kind: ControlMessageKind
    source: str
    target_session_id: str
    target_entity: str
    payload: dict[str, Any]
    force: bool
    timestamp: float
    trace_id: str


@dataclass(frozen=True)
class ControlMessageDeliveryResult:
    """投递结果。"""

    delivered: bool
    result: DeliveryResult
    detail: str = ""


@dataclass(frozen=True)
class ControlMessageEffectiveMask:
    """有效屏蔽集快照（不可变）。"""

    blocked_bits: int
    ignored_bits: int


@dataclass(frozen=False)
class UnkillableDeclaration:
    """UNKILLABLE 声明记录。

    非 frozen：force 通道清除保护时设置 is_active=False（不销毁声明，保留审计记录）。
    """

    entity_id: str
    entity_type: str
    declared_by: str
    is_active: bool
    declared_time: float


@dataclass(frozen=True)
class DeliveryDecisionRecord:
    """投递决策记录 — 供审计。"""

    decision_id: str
    kind: ControlMessageKind
    target_session_id: str
    target_entity: str
    priority_level: str
    blocked_status: str
    force_used: bool
    unkillable_cleared: bool
    delivery_result: DeliveryResult
    decision_time: float


@dataclass(frozen=True)
class FatalDiffuseRecord:
    """致命扩散记录。"""

    session_id: str
    kind: ControlMessageKind
    total_tasks: int
    cancelled_tasks: int
    failed_tasks: int
    diffuse_time: float


@dataclass
class ControlMessagePendingNode:
    """pending 队列节点 — 对标 sigqueue。

    非 frozen：标准消息去重时更新 info（保留最新 payload）与 insert_order。
    """

    kind: ControlMessageKind
    info: dict[str, Any]
    is_standard: bool
    is_realtime: bool
    insert_order: int


@dataclass(frozen=True)
class ControlMessagePendingView:
    """待处理队列快照视图。"""

    session_id: str
    nodes: tuple[ControlMessagePendingNode, ...]
    category_bitmap: int
    total_count: int


@dataclass(frozen=True)
class EnqueueResult:
    """入队结果。"""

    accepted: bool
    deduplicated: bool = False
    reason: str = ""


@dataclass(frozen=True)
class ProtectionResult:
    """UNKILLABLE 保护检查结果。"""

    action: ProtectionAction
    reason: str = ""
