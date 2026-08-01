"""ZG-6 系统生命周期状态机。

对标 Linux system_state（kernel.h:180）+ reboot/notifier/panic 机制。
核心不导入任何组件具体类，经 Protocol 接口交互。

投票类型（Vote/VoteResult/DuplicatePriorityError）自 ZG-4 起统一在
src.core.vote，此处从该模块转发导出（迁移期兼容 from src.core.system_state import Vote）。
"""

from src.core.vote import DuplicatePriorityError, Vote, VoteResult
from .history import TransitionHistory
from .notifier_chain import NotifierChain
from .state_machine import SystemStateMachine
from .types import (
    IllegalTransitionError,
    SystemLifecycleState,
    SystemLifecycleView,
    TransitionReason,
    TransitionRecord,
)

__all__ = [
    "DuplicatePriorityError",
    "IllegalTransitionError",
    "NotifierChain",
    "SystemLifecycleState",
    "SystemLifecycleView",
    "SystemStateMachine",
    "TransitionHistory",
    "TransitionReason",
    "TransitionRecord",
    "Vote",
    "VoteResult",
]
