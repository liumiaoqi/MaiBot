"""ZG-7 污染标记 — 不可逆污染位图系统。

对标 Linux tainted_mask（kernel/panic.c）+ TAINT_* 标志族 + panic_on_taint 动作映射：
系统运行中一旦进入不可信/被越界/带病的状态，即打上对应污染标志；
污染是历史烙记，只增不减，与"当前状态"正交。
"""

from src.core.tainted_mask.mark import mark_exception_swallowed, mark_taint
from src.core.tainted_mask.taint_action import TaintAction
from src.core.tainted_mask.taint_action_mapper import TaintActionMapper
from src.core.tainted_mask.taint_flag import TAINT_FLAGS_COUNT, TAINT_FLAGS_MAX, TaintFlag
from src.core.tainted_mask.tainted_mask import TaintedMask
from src.core.tainted_mask.types import TaintNotifyEvent, TaintRecord, TaintSubscriber

__all__ = [
    "TAINT_FLAGS_COUNT",
    "TAINT_FLAGS_MAX",
    "TaintAction",
    "mark_exception_swallowed",
    "mark_taint",
    "TaintActionMapper",
    "TaintFlag",
    "TaintNotifyEvent",
    "TaintRecord",
    "TaintSubscriber",
    "TaintedMask",
]
