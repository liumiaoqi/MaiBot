"""状态迁移通知链 — 优先级排序 + robust 回滚。

对标 Linux notifier_chain_register（kernel/notifier.c:17）+
notifier_call_chain_robust（kernel/notifier.c:114）。

ZG-4 语义修正（偏离 Linux，design.md §2.2）：robust 只在 BAD 时回滚，
STOP 只停止链不回滚——Linux 在 STOP_MASK（含 STOP）上回滚，此处有意偏离，
防后人照源码"修正"回来。
"""

import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable

from src.common.logger import get_logger
from src.core.system_state.types import (
    SystemLifecycleState,
    TransitionReason,
)
from src.core.vote import (
    DuplicatePriorityError,
    Vote,
    VoteHistory,
    VoteResult,
)

logger = get_logger(__name__)

# 优先级约定（数值小先通知，对标 Linux 高 priority 先）
PRIORITY_CRITICAL = 0
PRIORITY_HIGH = 10
PRIORITY_NORMAL = 20
PRIORITY_LOW = 30

# 订阅者返回 Vote 或 VoteResult（VoteResult 用于 BAD 携带原因）
CallbackType = Callable[
    [SystemLifecycleState, SystemLifecycleState, TransitionReason],
    Awaitable[Vote | VoteResult] | Vote | VoteResult,
]
RollbackType = Callable[[], Awaitable[None]]


@dataclass
class _Subscriber:
    """订阅者条目（通知链内部）。"""

    callback: CallbackType
    priority: int
    seq: int
    on_rollback: RollbackType | None = None


@dataclass
class SubscriberInfo:
    """订阅者内省信息（NFR-ZG4-MNT-02）。"""

    name: str
    priority: int
    has_on_rollback: bool


class NotifierChain:
    """状态迁移通知链。

    普通模式（notify）：遍历通知收集投票，不停止链，不回滚（保留现状）。
    robust 模式（notify_robust）：STOP/BAD 停止链，仅 BAD 触发逆序回滚
    已成功者的 on_rollback（不回滚触发者本身），best-effort。
    nofail 模式（notify_nofail）：遍历到底不停止，异常/BAD 记告警，不回滚。
    """

    def __init__(self, timeout: float = 5.0, vote_history_capacity: int = 100) -> None:
        self._subscribers: list[_Subscriber] = []
        self._seq_counter = 0
        self._timeout = timeout
        self._history = VoteHistory(vote_history_capacity)

    def register(
        self,
        callback: CallbackType,
        priority: int = PRIORITY_NORMAL,
        on_rollback: RollbackType | None = None,
        unique_priority: bool = False,
    ) -> _Subscriber:
        """按 priority 升序插入（机制 1），同优先级按注册顺序。

        Args:
            unique_priority: True 时同优先级重复注册抛 DuplicatePriorityError
                （对标 Linux atomic_notifier_chain_register_unique_prio），
                用于"只能有一个高优先级守卫"的场景。
        """
        if unique_priority:
            for existing in self._subscribers:
                if existing.priority == priority:
                    name = getattr(existing.callback, "__name__", "<anonymous>")
                    raise DuplicatePriorityError(priority, name)
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
    ) -> list[tuple[_Subscriber, Vote]]:
        """普通模式：遍历通知收集投票，不停止链，不回滚。

        异常隔离：订阅者抛异常视为 DONE，记日志（NFR-ZG4-REL-01）。
        """
        results: list[tuple[_Subscriber, Vote]] = []
        for subscriber in list(self._subscribers):
            vote, _ = await self._call_subscriber(subscriber, old, new, reason)
            results.append((subscriber, vote))
        # 内省历史：聚合结果（收集模式无停止语义，final_vote 取最后一个停止票）
        final_vote = Vote.DONE
        for _, vote in results:
            if vote.is_stop:
                final_vote = vote
        self._history.append(VoteResult(final_vote=final_vote))
        return results

    async def notify_robust(
        self,
        old: SystemLifecycleState,
        new: SystemLifecycleState,
        reason: TransitionReason,
    ) -> VoteResult:
        """robust 模式：STOP/BAD 停止链，仅 BAD 触发逆序回滚已成功者。

        返回 VoteResult：
        - 全部放行 → final_vote=Vote.OK
        - STOP 中止 → final_vote=Vote.STOP（vetoer，rolled_back=False，不回滚）
        - BAD 否决 → final_vote=Vote.BAD（vetoer/reason，rolled_back=True，已回滚）

        偏离 Linux（design.md §2.2）：只在 BAD 时回滚，STOP 只停止链。
        """
        notified: list[_Subscriber] = []
        for subscriber in list(self._subscribers):
            vote, cb_reason = await self._call_subscriber(subscriber, old, new, reason)
            name = getattr(subscriber.callback, "__name__", "<anonymous>")
            if vote is Vote.STOP:
                # 干净中止：不回滚（design.md §2.2 偏离）
                result = VoteResult(final_vote=Vote.STOP, vetoer=name)
                self._history.append(result)
                return result
            if vote is Vote.BAD:
                # 逆序回滚已成功者（不回滚触发 BAD 者本身，机制 2）
                for prepared in reversed(notified):
                    await self._rollback_one(prepared)
                bad_reason: BaseException | str = (
                    cb_reason if cb_reason is not None else "BAD without reason"
                )
                if cb_reason is None:
                    logger.warning("订阅者 %s 返回 BAD 未携带原因，降级为默认字符串", name)
                logger.warning(
                    "状态迁移被订阅者 %s BAD 否决（%s），已逆序回滚",
                    name, bad_reason,
                    exc_info=cb_reason if isinstance(cb_reason, BaseException) else None,
                )
                result = VoteResult(
                    final_vote=Vote.BAD,
                    vetoer=name,
                    reason=bad_reason,
                    rolled_back=True,
                )
                self._history.append(result)
                return result
            notified.append(subscriber)
        result = VoteResult(final_vote=Vote.OK)
        self._history.append(result)
        return result

    async def notify_nofail(
        self,
        old: SystemLifecycleState,
        new: SystemLifecycleState,
        reason: TransitionReason,
    ) -> VoteResult:
        """nofail 模式：遍历到底不停止，异常/BAD 记告警，不回滚。

        用于关机/清理阶段。返回 VoteResult.failures 含所有失败记录
        （handler name + 异常/原因）；final_vote 为最后一个 BAD 或 DONE
        （无 BAD 时）。BAD 不当作 DONE 静默放行（spec 5.5.1-4）。
        """
        failures: list[tuple[str, BaseException | str]] = []
        last_bad: str | None = None
        for subscriber in list(self._subscribers):
            vote, cb_reason = await self._call_subscriber(subscriber, old, new, reason)
            name = getattr(subscriber.callback, "__name__", "<anonymous>")
            if vote is Vote.BAD:
                bad_reason: BaseException | str = (
                    cb_reason if cb_reason is not None else "BAD without reason"
                )
                failures.append((name, bad_reason))
                last_bad = name
                logger.warning(
                    "nofail: 订阅者 %s 返回 BAD（%s），继续遍历",
                    name, bad_reason,
                    exc_info=cb_reason if isinstance(cb_reason, BaseException) else None,
                )
            elif cb_reason is not None:
                # 异常视为 DONE 但记录失败（nofail 不静默吞没，spec 5.5.1-2）
                failures.append((name, cb_reason))
        result = VoteResult(
            # 聚合规则（spec 5.5.2-1）：最后一个 BAD 或 DONE（无 BAD 时），
            # 异常计入 failures 但不改变 final_vote
            final_vote=Vote.BAD if last_bad is not None else Vote.DONE,
            vetoer=last_bad,
            failures=failures,
        )
        self._history.append(result)
        return result

    # ── 内省（NFR-ZG4-MNT-02）──────────────────────────────

    def get_subscriber_list(self) -> list[SubscriberInfo]:
        """返回链上订阅者（含 name/priority/has_on_rollback）。"""
        return [
            SubscriberInfo(
                name=getattr(s.callback, "__name__", "<anonymous>"),
                priority=s.priority,
                has_on_rollback=s.on_rollback is not None,
            )
            for s in self._subscribers
        ]

    def get_vote_history(self) -> list[VoteResult]:
        """返回最近 N 次投票结果。"""
        return self._history.get_all()

    # ── 内部 ──────────────────────────────────────────────

    async def _call_subscriber(
        self,
        subscriber: _Subscriber,
        old: SystemLifecycleState,
        new: SystemLifecycleState,
        reason: TransitionReason,
    ) -> tuple[Vote, BaseException | str | None]:
        """调用单个订阅者，超时视为 DONE，异常隔离。

        返回 (vote, reason)：reason 仅异常（视为 DONE）或 VoteResult 携带时
        有值，供 nofail 聚合失败记录。
        """
        try:
            result = subscriber.callback(old, new, reason)
            if asyncio.iscoroutine(result):
                result = await asyncio.wait_for(result, timeout=self._timeout)
            if isinstance(result, VoteResult):
                return result.final_vote, result.reason
            return Vote(result), None
        except asyncio.TimeoutError:
            logger.warning("状态迁移通知超时，视为 DONE（订阅者 priority=%d）", subscriber.priority)
            return Vote.DONE, None
        except Exception as exc:
            from src.core.tainted_mask.mark import mark_exception_swallowed
            mark_exception_swallowed()
            logger.exception("状态迁移订阅者异常，已隔离（priority=%d）", subscriber.priority)
            return Vote.DONE, exc

    async def _rollback_one(self, subscriber: _Subscriber) -> None:
        """对单个已准备订阅者调 on_rollback（None 时 no-op），best-effort。"""
        if subscriber.on_rollback is None:
            return
        try:
            result = subscriber.on_rollback()
            if asyncio.iscoroutine(result):
                await asyncio.wait_for(result, timeout=self._timeout)
        except Exception:
            from src.core.tainted_mask.mark import mark_exception_swallowed
            mark_exception_swallowed()
            logger.exception("状态迁移回滚异常（priority=%d），回滚继续", subscriber.priority)
