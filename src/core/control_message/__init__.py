"""ZG-8 控制消息优先级 — 控制消息的优先级投递、屏蔽、UNKILLABLE 保护、force 强制投递。

对标 Linux 内核信号机制（signal.c）：带优先级、可屏蔽、有不可捕获特权通道的事件投递系统。
"""

from .types import (
    REALTIME_MASK,
    STANDARD_MASK,
    SYNCHRONOUS_MASK,
    UNMASKABLE_MASK,
    ControlMessage,
    ControlMessageCategory,
    ControlMessageDeliveryResult,
    ControlMessageEffectiveMask,
    ControlMessageKind,
    ControlMessagePendingNode,
    ControlMessagePendingView,
    DeliveryDecisionRecord,
    DeliveryResult,
    EnqueueResult,
    FatalDiffuseRecord,
    MaskOperation,
    MaskScope,
    ProtectionAction,
    ProtectionResult,
    UnkillableDeclaration,
)

__all__ = [
    "ControlMessage",
    "ControlMessageCategory",
    "ControlMessageDeliveryResult",
    "ControlMessageEffectiveMask",
    "ControlMessageKind",
    "ControlMessagePendingNode",
    "ControlMessagePendingView",
    "DeliveryDecisionRecord",
    "DeliveryResult",
    "EnqueueResult",
    "FatalDiffuseRecord",
    "MaskOperation",
    "MaskScope",
    "ProtectionAction",
    "ProtectionResult",
    "REALTIME_MASK",
    "STANDARD_MASK",
    "SYNCHRONOUS_MASK",
    "UNMASKABLE_MASK",
    "UnkillableDeclaration",
]
