"""通知链单元测试（ZG-6 Task 10 + ZG-4 Task 10 改写）。

ZG-4 语义修正（design.md §2.2）：robust 只在 BAD 时回滚，STOP 只停止链
不回滚——原"STOP 触发回滚"断言已改写为 BAD 触发（预期内的语义修正）。

覆盖：优先级排序（AC-ADAPT-02）、STOP 干净中止/BAD 否决回滚、
nofail 遍历到底、unique_priority 去重、异常隔离（NFR-ZG6-REL-01）、
取消订阅（AC-ADAPT-04）、内省（NFR-ZG4-MNT-02）。
"""

import asyncio

from src.core.system_state.notifier_chain import DuplicatePriorityError, NotifierChain
from src.core.system_state.types import (
    SystemLifecycleState,
    TransitionReason,
)
from src.core.vote import Vote, VoteResult

OLD = SystemLifecycleState.READY
NEW = SystemLifecycleState.SHUTTING_DOWN
REASON = TransitionReason.SHUTDOWN_SIGNAL


def _record(log: list[str], name: str):
    async def sub(old, new, reason):
        log.append(name)
        return Vote.DONE

    return sub


def _appended(log: list[str], name: str):
    log.append(name)


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


async def test_stop_vote_clean_stop_no_rollback():
    """REQ-ZG4-ROBUST-01: robust 模式 STOP → 干净中止，不回滚。"""
    chain = NotifierChain()
    rolled_back: list[str] = []

    async def blocker(old, new, reason):
        return Vote.STOP

    async def prepared(old, new, reason):
        return Vote.DONE

    chain.register(prepared, priority=10, on_rollback=lambda: _appended(rolled_back, "prepared"))
    chain.register(blocker, priority=20)
    chain.register(prepared, priority=30, on_rollback=lambda: _appended(rolled_back, "never-called"))

    result = await chain.notify_robust(OLD, NEW, REASON)
    assert result.final_vote is Vote.STOP
    assert result.vetoer == "blocker"
    assert not result.rolled_back  # STOP 不回滚（修正前会回滚）
    assert rolled_back == []  # 无任何 on_rollback 被调用


async def test_bad_vetoes_robust_with_rollback():
    """REQ-ZG4-ROBUST-01/02/03: BAD 否决 → 停止链 + 逆序回滚已成功者。"""
    chain = NotifierChain()
    rolled_back: list[str] = []

    async def blocker(old, new, reason):
        return VoteResult(final_vote=Vote.BAD, reason=ValueError("设备类型变更被否决"))

    async def prepared(old, new, reason):
        return Vote.DONE

    chain.register(prepared, priority=10, on_rollback=lambda: _appended(rolled_back, "prepared"))
    chain.register(blocker, priority=20)
    chain.register(prepared, priority=30, on_rollback=lambda: _appended(rolled_back, "never-called"))

    result = await chain.notify_robust(OLD, NEW, REASON)
    assert result.final_vote is Vote.BAD
    assert result.vetoer == "blocker"
    assert result.rolled_back
    assert "ValueError" in result.serialize_reason()
    assert rolled_back == ["prepared"]  # 仅逆序回滚已成功者，不含否决者与未通知者


async def test_stop_ignored_health_change():
    """AC-ZG6-ADAPT-01-3: 普通模式 STOP 不否决，仅作为投票记录。"""
    chain = NotifierChain()

    async def blocker(old, new, reason):
        return Vote.STOP

    async def normal(old, new, reason):
        return Vote.DONE

    chain.register(blocker, priority=10)
    chain.register(normal, priority=20)
    results = await chain.notify(OLD, NEW, REASON)
    assert len(results) == 2
    assert results[0][1] == Vote.STOP  # 不阻断后续
    assert results[1][1] == Vote.DONE


async def test_robust_rollback_bad_trigger():
    """REQ-ZG4-ROBUST-03: BAD 触发逆序回滚（后成功者先回滚）。"""
    chain = NotifierChain()
    rollback_log: list[str] = []

    async def sub_a(old, new, reason):
        return Vote.DONE

    async def sub_b(old, new, reason):
        return Vote.DONE

    async def sub_c(old, new, reason):
        return VoteResult(final_vote=Vote.BAD)

    chain.register(sub_a, priority=10, on_rollback=lambda: _appended(rollback_log, "a"))
    chain.register(sub_b, priority=20, on_rollback=lambda: _appended(rollback_log, "b"))
    chain.register(sub_c, priority=30)

    result = await chain.notify_robust(OLD, NEW, REASON)
    assert result.final_vote is Vote.BAD
    assert result.rolled_back
    assert rollback_log == ["b", "a"]  # 逆序：后通知者先回滚


async def test_rollback_best_effort():
    """AC-ZG6-LIFE-03-2/NFR-ZG4-REL-02: 回滚异常不阻断（best-effort）。"""
    chain = NotifierChain()
    rollback_log: list[str] = []

    async def sub_boom(old, new, reason):
        return Vote.DONE

    async def sub_block(old, new, reason):
        return VoteResult(final_vote=Vote.BAD, reason=RuntimeError("否决"))

    def on_rollback_boom():
        rollback_log.append("boom-start")
        raise RuntimeError("回滚失败")

    chain.register(sub_boom, priority=10, on_rollback=on_rollback_boom)
    chain.register(sub_block, priority=20)
    result = await chain.notify_robust(OLD, NEW, REASON)
    assert result.final_vote is Vote.BAD
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
    assert results[0][1] == Vote.DONE  # 异常视为 DONE


async def test_subscriber_timeout_treated_as_done():
    """通知超时记告警并视为 DONE。"""
    chain = NotifierChain(timeout=0.01)

    async def sub_slow(old, new, reason):
        await asyncio.sleep(1.0)
        return Vote.DONE

    chain.register(sub_slow)
    results = await chain.notify(OLD, NEW, REASON)
    assert results[0][1] == Vote.DONE


async def test_sync_callback_supported():
    """同步回调也可注册（返回 Vote 或可转义值）。"""
    chain = NotifierChain()
    log: list[str] = []

    def sync_sub(old, new, reason):
        log.append("sync")
        return Vote.DONE

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


# ── ZG-4 新增用例 ─────────────────────────────────────────

async def test_bad_carries_reason():
    """REQ-ZG4-VOTE-04: BAD 携带异常/字符串原因。"""
    chain = NotifierChain()

    async def sub_bad(old, new, reason):
        return VoteResult(final_vote=Vote.BAD, reason=ValueError("具体原因"))

    chain.register(sub_bad)
    result = await chain.notify_robust(OLD, NEW, REASON)
    assert result.reason is not None
    assert "具体原因" in result.serialize_reason()


async def test_vote_stop_mask():
    """REQ-ZG4-VOTE-02: STOP_MASK 判定。"""
    assert Vote.STOP.is_stop and Vote.BAD.is_stop
    assert not Vote.DONE.is_stop and not Vote.OK.is_stop


async def test_unique_priority():
    """REQ-ZG4-REG-01/03: unique_priority 去重 + 冲突报错。"""
    chain = NotifierChain()

    async def sub_a(old, new, reason):
        return Vote.DONE

    async def sub_b(old, new, reason):
        return Vote.DONE

    chain.register(sub_a, priority=10, unique_priority=True)
    try:
        chain.register(sub_b, priority=10, unique_priority=True)
        raise AssertionError("应抛 DuplicatePriorityError")
    except DuplicatePriorityError as e:
        assert e.priority == 10
        assert e.existing_name == "sub_a"  # 按 callback.__name__ 标识
    assert len(chain.get_subscriber_list()) == 1  # A 保留


async def test_default_no_unique_priority():
    """REQ-ZG4-REG-02: 默认不去重，同优先级按注册顺序。"""
    chain = NotifierChain()
    log: list[str] = []
    chain.register(_record(log, "a"), priority=10)
    chain.register(_record(log, "b"), priority=10)
    await chain.notify(OLD, NEW, REASON)
    assert log == ["a", "b"]


async def test_nofail_continues_on_bad():
    """REQ-ZG4-NOFAIL-01/03: nofail 遍历到底，BAD 不停止链不回滚。"""
    chain = NotifierChain()
    log: list[str] = []
    rolled: list[str] = []

    async def sub_bad(old, new, reason):
        log.append("bad")
        return VoteResult(final_vote=Vote.BAD, reason="失败1")

    chain.register(sub_bad, priority=10, on_rollback=lambda: _appended(rolled, "bad"))
    chain.register(_record(log, "after"), priority=20, on_rollback=lambda: _appended(rolled, "after"))

    result = await chain.notify_nofail(OLD, NEW, REASON)
    assert log == ["bad", "after"]  # 遍历到底
    assert result.final_vote is Vote.BAD
    assert len(result.failures) == 1
    assert result.failures[0][0] == "sub_bad"
    assert rolled == []  # nofail 不回滚


async def test_nofail_no_silent_swallow():
    """REQ-ZG4-NOFAIL-02/04: nofail 失败记告警不静默，异常也进 failures。"""
    chain = NotifierChain()

    async def sub_broken(old, new, reason):
        raise RuntimeError("清理失败")

    chain.register(sub_broken)
    result = await chain.notify_nofail(OLD, NEW, REASON)
    assert len(result.failures) == 1
    assert isinstance(result.failures[0][1], RuntimeError)
    assert result.final_vote is Vote.DONE  # 无 BAD 时 DONE


async def test_non_robust_no_rollback():
    """REQ-ZG4-ROBUST-06: 普通 notify 遇 BAD 不回滚。"""
    chain = NotifierChain()
    rolled: list[str] = []

    async def sub_ok(old, new, reason):
        return Vote.OK

    async def sub_bad(old, new, reason):
        return VoteResult(final_vote=Vote.BAD)

    chain.register(sub_ok, priority=10, on_rollback=lambda: _appended(rolled, "ok"))
    chain.register(sub_bad, priority=20)
    results = await chain.notify(OLD, NEW, REASON)
    assert results[1][1] is Vote.BAD  # 普通模式收集全部投票
    assert rolled == []  # 不回滚


async def test_rollback_skip_no_callback():
    """REQ-ZG4-ROBUST-05: 无 on_rollback 跳过。"""
    chain = NotifierChain()
    rolled: list[str] = []

    async def sub_no_rb(old, new, reason):
        return Vote.DONE

    async def sub_with_rb(old, new, reason):
        return Vote.DONE

    async def sub_bad(old, new, reason):
        return VoteResult(final_vote=Vote.BAD)

    chain.register(sub_no_rb, priority=10)  # 无 on_rollback
    chain.register(sub_with_rb, priority=20, on_rollback=lambda: _appended(rolled, "with"))
    chain.register(sub_bad, priority=30)
    result = await chain.notify_robust(OLD, NEW, REASON)
    assert result.rolled_back
    assert rolled == ["with"]  # 跳过无回调者，回滚有回调者


async def test_notifier_introspection():
    """NFR-ZG4-MNT-02: 订阅者列表 + 投票历史非空。"""
    chain = NotifierChain()

    async def sub(old, new, reason):
        return Vote.DONE

    chain.register(sub, priority=10, on_rollback=lambda: None)
    infos = chain.get_subscriber_list()
    assert len(infos) == 1
    assert infos[0].name == "sub"
    assert infos[0].priority == 10
    assert infos[0].has_on_rollback

    await chain.notify(OLD, NEW, REASON)
    history = chain.get_vote_history()
    assert len(history) == 1
    assert history[0].final_vote is Vote.DONE
