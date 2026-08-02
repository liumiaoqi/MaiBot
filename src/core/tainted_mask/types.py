"""ZG-7 污染标记 — 数据结构定义。

对标 Linux tainted_mask（kernel/panic.c）：
- TaintRecord 对标每位污染的首次记录（时间戳 + 调用栈）
- TaintNotifyEvent 对标 panic_notifier_list 的通知事件
- TaintSubscriber 为订阅回调类型别名
"""

from dataclasses import dataclass
from typing import Awaitable, Callable

from src.core.tainted_mask.taint_action import TaintAction
from src.core.tainted_mask.taint_flag import TaintFlag


@dataclass(frozen=True)
class TaintRecord:
    """单次首次置位记录（spec §3.4）。

    frozen 保证快照不可变；首次置位后不再更新（spec §2.1.1 规则 3）。
    """

    flag: TaintFlag
    first_ts: float
    first_stack: str
    action_taken: TaintAction


@dataclass(frozen=True)
class TaintNotifyEvent:
    """污染位变化通知事件（spec §3.5）。

    首次置位时广播；幂等置位不广播（spec §2.1.1 规则 2）。
    """

    flag: TaintFlag
    first_ts: float
    current_mask: int


# 订阅回调类型别名（design §6.1.1）：同步或异步回调均可
TaintSubscriber = Callable[[TaintNotifyEvent], Awaitable[None] | None]
