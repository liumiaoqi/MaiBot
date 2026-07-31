"""ZG-6 系统生命周期状态机。

对标 Linux system_state（kernel.h:180）+ reboot/notifier/panic 机制。
核心不导入任何组件具体类，经 Protocol 接口交互。
"""

from .history import TransitionHistory
from .notifier_chain import NotifierChain
from .state_machine import SystemStateMachine
from .types import (
    IllegalTransitionError,
    SystemLifecycleState,
    SystemLifecycleView,
    TransitionReason,
    TransitionRecord,
    TransitionVote,
)

__all__ = [
    "IllegalTransitionError",
    "NotifierChain",
    "SystemLifecycleState",
    "SystemLifecycleView",
    "SystemStateMachine",
    "TransitionHistory",
    "TransitionReason",
    "TransitionRecord",
    "TransitionVote",
]
