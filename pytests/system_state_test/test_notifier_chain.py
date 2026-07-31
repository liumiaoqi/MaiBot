"""通知链单元测试（ZG-6 Task 10）。

覆盖：优先级排序（AC-ADAPT-02）、STOP 否决与忽略（AC-ADAPT-01-2/3）、
robust 逆序回滚（AC-LIFE-03）、异常隔离（NFR-ZG6-REL-01）、
取消订阅（AC-ADAPT-04）。
"""

import asyncio

from src.core.system_state.notifier_chain import NotifierChain
from src.core.system_state.types import (
    SystemLifecycleState,
    TransitionReason,
    TransitionVote,
)

OLD = SystemLifecycleState.READY
NEW = SystemLifecycleState.SHUTTING_DOWN
REASON = TransitionReason.SHUTDOWN_SIGNAL


def _record(log: list[str], name: str):
    async def sub(old, new, reason):
        log.append(name)
        return TransitionVote.DONE

    return sub


async def test_priority_ordering():
    """AC-ZG6-ADAPT-02-1: 优先级升序通知（数值小先通知）。"""
    chain = NotifierChain()
    log: list[str] = []
    chain.register(_record(log, "low"), priority=30)
    chain.register(_record(log, "high"), priority=10)
    chain.register(_record(log, "normal"), priority=20)
    await chain.notify(OLD, NEW, REASON)
    assert log == ["high", "normal", "low"]


async def test_same_priority_fifo():
    """AC-ZG6-ADAPT-02-2: 同优先级按注册顺序 FIFO。"""
    chain = NotifierChain()
    log: list[str] = []
    chain.register(_record(log, "first"), priority=20)
    chain.register(_record(log, "second"), priority=20)
    chain.register(_record(log, "third"), priority=20)
    await chain.notify(OLD, NEW, REASON)
    assert log == ["first", "second", "third"]


async def test_stop_vote_vetoes_robust():
    """AC-ZG6-ADAPT-01-2: robust 模式 STOP 否决 → False + 逆序回滚已成功者。"""
    chain = NotifierChain()
    rolled_back: list[str] = []

    async def blocker(old, new, reason):
        return TransitionVote.STOP

    async def prepared(old, new, reason):
        return TransitionVote.DONE

    chain.register(prepared, priority=10, on_rollback=lambda: _appended(rolled_back, "prepared"))
    chain.register(blocker, priority=20)
    chain.register(prepared, priority=30, on_rollback=lambda: _appended(rolled_back, "never-called"))

    ok = await chain.notify_robust(OLD, NEW, REASON)
    assert ok is False
    assert rolled_back == ["prepared"]  # 仅逆序回滚已成功者，不含否决者与未通知者


def _appended(log: list[str], name: str):
    log.append(name)


async def test_stop_ignored_health_change():
    """AC-ZG6-ADAPT-01-3: 普通模式 STOP 不否决，仅作为投票记录。"""
    chain = NotifierChain()

    async def blocker(old, new, reason):
        return TransitionVote.STOP

    async def normal(old, new, reason):
        return TransitionVote.DONE

    chain.register(blocker, priority=10)
    chain.register(normal, priority=20)
    results = await chain.notify(OLD, NEW, REASON)
    assert len(results) == 2
    assert results[0][1] == TransitionVote.STOP  # 不阻断后续
    assert results[1][1] == TransitionVote.DONE


async def test_robust_rollback():
    """AC-ZG6-LIFE-03-1: robust 逆序回滚（后成功者先回滚）。"""
    chain = NotifierChain()
    rollback_log: list[str] = []

    async def sub_a(old, new, reason):
        return TransitionVote.DONE

    async def sub_b(old, new, reason):
        return TransitionVote.DONE

    async def sub_c(old, new, reason):
        return TransitionVote.STOP

    chain.register(sub_a, priority=10, on_rollback=lambda: _appended(rollback_log, "a"))
    chain.register(sub_b, priority=20, on_rollback=lambda: _appended(rollback_log, "b"))
    chain.register(sub_c, priority=30)

    ok = await chain.notify_robust(OLD, NEW, REASON)
    assert ok is False
    assert rollback_log == ["b", "a"]  # 逆序：后通知者先回滚


async def test_rollback_best_effort():
    """AC-ZG6-LIFE-03-2: 回滚异常不阻断（best-effort）。"""
    chain = NotifierChain()
    rollback_log: list[str] = []

    async def sub_boom(old, new, reason):
        return TransitionVote.DONE

    async def sub_block(old, new, reason):
        return TransitionVote.STOP

    def on_rollback_boom():
        rollback_log.append("boom-start")
        raise RuntimeError("回滚失败")

    chain.register(sub_boom, priority=10, on_rollback=on_rollback_boom)
    chain.register(sub_block, priority=20)
    ok = await chain.notify_robust(OLD, NEW, REASON)
    assert ok is False
    assert rollback_log == ["boom-start"]  # 异常被隔离，流程不中断


async def test_subscriber_exception_isolation():
    """NFR-ZG6-REL-01: 订阅者异常隔离，后续订阅者仍被通知，投票视为 DONE。"""
    chain = NotifierChain()
    log: list[str] = []

    async def sub_broken(old, new, reason):
        raise RuntimeError("订阅者崩溃")

    chain.register(sub_broken, priority=10)
    chain.register(_record(log, "after"), priority=20)
    results = await chain.notify(OLD, NEW, REASON)
    assert log == ["after"]
    assert len(results) == 2
    assert results[0][1] == TransitionVote.DONE  # 异常视为 DONE


async def test_subscriber_timeout_treated_as_done():
    """通知超时记告警并视为 DONE。"""
    chain = NotifierChain(timeout=0.01)

    async def sub_slow(old, new, reason):
        await asyncio.sleep(1.0)
        return TransitionVote.DONE

    results = await chain.notify(OLD, NEW, REASON)
    assert results[0][1] == TransitionVote.DONE


async def test_sync_callback_supported():
    """同步回调也可注册（返回 TransitionVote 或可转义值）。"""
    chain = NotifierChain()
    log: list[str] = []

    def sync_sub(old, new, reason):
        log.append("sync")
        return TransitionVote.DONE

    chain.register(sync_sub)
    await chain.notify(OLD, NEW, REASON)
    assert log == ["sync"]


async def test_unsubscribe():
    """AC-ZG6-ADAPT-04-1/2: 取消订阅后不再通知；未注册取消无副作用。"""
    chain = NotifierChain()
    log: list[str] = []

    async def sub_a(old, new, reason):
        log.append("a")

    async def sub_b(old, new, reason):
        log.append("b")

    sub_a_handle = chain.register(sub_a, priority=10)
    chain.register(sub_b, priority=20)

    chain.unregister(sub_a_handle)
    await chain.notify(OLD, NEW, REASON)
    assert log == ["b"]

    chain.unregister(sub_a_handle)  # 重复取消无副作用
    await chain.notify(OLD, NEW, REASON)
    assert log == ["b", "b"]
