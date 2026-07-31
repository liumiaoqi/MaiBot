"""状态迁移通知链 — 优先级排序 + robust 回滚。

对标 Linux notifier_chain_register（kernel/notifier.c:17）+
notifier_call_chain_robust（kernel/notifier.c:114）。
"""

import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable

from src.common.logger import get_logger
from src.core.system_state.types import (
    SystemLifecycleState,
    TransitionReason,
    TransitionVote,
)

logger = get_logger(__name__)

# 优先级约定（数值小先通知，对标 Linux 高 priority 先）
PRIORITY_CRITICAL = 0
PRIORITY_HIGH = 10
PRIORITY_NORMAL = 20
PRIORITY_LOW = 30

CallbackType = Callable[
    [SystemLifecycleState, SystemLifecycleState, TransitionReason],
    Awaitable[TransitionVote] | TransitionVote,
]
RollbackType = Callable[[], Awaitable[None]]


@dataclass
class _Subscriber:
    """订阅者条目（通知链内部）。"""

    callback: CallbackType
    priority: int
    seq: int
    on_rollback: RollbackType | None = None


class NotifierChain:
    """状态迁移通知链。

    普通模式（notify）：遍历通知收集投票，异常隔离。
    robust 模式（notify_robust）：某订阅者 STOP 时逆序调已成功者的
    on_rollback 回滚（不回滚失败者本身），best-effort。
    """

    def __init__(self, timeout: float = 5.0) -> None:
        self._subscribers: list[_Subscriber] = []
        self._seq_counter = 0
        self._timeout = timeout

    def register(
        self,
        callback: CallbackType,
        priority: int = PRIORITY_NORMAL,
        on_rollback: RollbackType | None = None,
    ) -> _Subscriber:
        """按 priority 升序插入（机制 1），同优先级按注册顺序。"""
        subscriber = _Subscriber(
            callback=callback, priority=priority, seq=self._seq_counter, on_rollback=on_rollback
        )
        self._seq_counter += 1
        self._subscribers.append(subscriber)
        self._subscribers.sort(key=lambda s: (s.priority, s.seq))
        return subscriber

    def unregister(self, subscriber: _Subscriber) -> None:
        """移除订阅者，不存在时无副作用。"""
        try:
            self._subscribers.remove(subscriber)
        except ValueError:
            pass

    async def notify(
        self,
        old: SystemLifecycleState,
        new: SystemLifecycleState,
        reason: TransitionReason,
    ) -> list[tuple[_Subscriber, TransitionVote]]:
        """普通模式：遍历通知，收集投票。异常隔离（NFR-ZG6-REL-01）。"""
        results: list[tuple[_Subscriber, TransitionVote]] = []
        for subscriber in list(self._subscribers):
            vote = await self._call_subscriber(subscriber, old, new, reason)
            results.append((subscriber, vote))
        return results

    async def notify_robust(
        self,
        old: SystemLifecycleState,
        new: SystemLifecycleState,
        reason: TransitionReason,
    ) -> bool:
        """robust 模式：STOP 时逆序回滚已成功者（机制 2）。

        返回 True=全部放行，False=被否决（已回滚）。
        回滚 best-effort：on_rollback 异常不阻断回滚流程。
        """
        notified: list[_Subscriber] = []
        for subscriber in list(self._subscribers):
            vote = await self._call_subscriber(subscriber, old, new, reason)
            if vote == TransitionVote.STOP:
                # 逆序回滚已成功者（不含失败者本身）
                for prepared in reversed(notified):
                    await self._rollback_one(prepared)
                return False
            notified.append(subscriber)
        return True

    # ── 内部 ──────────────────────────────────────────────

    async def _call_subscriber(
        self,
        subscriber: _Subscriber,
        old: SystemLifecycleState,
        new: SystemLifecycleState,
        reason: TransitionReason,
    ) -> TransitionVote:
        """调用单个订阅者，超时视为 DONE，异常隔离。"""
        try:
            result = subscriber.callback(old, new, reason)
            if asyncio.iscoroutine(result):
                result = await asyncio.wait_for(result, timeout=self._timeout)
            return TransitionVote(result)
        except asyncio.TimeoutError:
            logger.warning("状态迁移通知超时，视为 DONE（订阅者 priority=%d）", subscriber.priority)
            return TransitionVote.DONE
        except Exception:
            logger.exception("状态迁移订阅者异常，已隔离（priority=%d）", subscriber.priority)
            return TransitionVote.DONE

    async def _rollback_one(self, subscriber: _Subscriber) -> None:
        """对单个已准备订阅者调 on_rollback（None 时 no-op），best-effort。"""
        if subscriber.on_rollback is None:
            return
        try:
            result = subscriber.on_rollback()
            if asyncio.iscoroutine(result):
                await asyncio.wait_for(result, timeout=self._timeout)
        except Exception:
            logger.exception("状态迁移回滚异常（priority=%d），回滚继续", subscriber.priority)
