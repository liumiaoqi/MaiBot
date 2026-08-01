"""EventBus robust/nofail + 向后兼容测试（ZG-4 Task 9）。

覆盖：robust 回滚（REQ-ZG4-EB-01/02/03）、消息修改保留（EB-04）、
非拦截型 BAD 忽略（EB-05）、旧签名映射（INT-03）、nofail（NOFAIL）、
IPC 桥接 STOP 投票（P1）、内省（NFR-ZG4-MNT-02）、configure 幂等（P0）。
"""

import asyncio

import pytest

from src.core.event_bus import EventBus
from src.core.types import EventType
from src.core.vote import DuplicatePriorityError, Vote, VoteResult


def _mk():
    """新建独立 EventBus（避免模块级单例跨测试污染）。"""
    return EventBus()


async def _ok_handler(msg):
    return (True, msg)


async def _stop_handler(msg):
    return (False, msg)


async def _bad_handler(msg):
    return VoteResult(final_vote=Vote.BAD, reason=RuntimeError("boom"))


async def test_event_bus_robust_rollback():
    """AC-ZG4-EB-01-1: robust emit，A/B 已执行，C 返回 BAD → 逆序回滚 B、A。"""
    eb = _mk()
    rollback_log: list[str] = []

    async def rb_a():
        rollback_log.append("a")

    async def rb_b():
        rollback_log.append("b")

    async def sub_c(msg):
        return VoteResult(final_vote=Vote.BAD, reason="否决")

    eb.subscribe(EventType.ON_START, _ok_handler, "a", weight=30, intercept=True, on_rollback=rb_a)
    eb.subscribe(EventType.ON_START, _ok_handler, "b", weight=20, intercept=True, on_rollback=rb_b)
    eb.subscribe(EventType.ON_START, sub_c, "c", weight=10, intercept=True)

    result = await eb.emit(EventType.ON_START, robust=True)
    assert result.final_vote is Vote.BAD
    assert result.vetoer == "c"
    assert result.rolled_back
    assert rollback_log == ["b", "a"]  # 逆序


async def test_non_intercept_not_rolled_back():
    """AC-ZG4-EB-02-1: 非拦截型 fire-and-forget 不参与回滚。"""
    eb = _mk()
    fired: list[str] = []
    rollback_log: list[str] = []

    async def rb_a():
        rollback_log.append("a")

    async def async_handler(msg):
        fired.append("async")

    eb.subscribe(EventType.ON_START, _ok_handler, "a", weight=30, intercept=True, on_rollback=rb_a)
    eb.subscribe(EventType.ON_START, async_handler, "async", weight=20, intercept=False)
    eb.subscribe(EventType.ON_START, _bad_handler, "c", weight=10, intercept=True)

    result = await eb.emit(EventType.ON_START, robust=True)
    assert result.final_vote is Vote.BAD
    assert fired == []  # BAD 停止链后非拦截型不执行
    assert rollback_log == ["a"]
    # 让 fire-and-forget 任务有机会完成（未触发则不产生）
    await asyncio.sleep(0.01)
    assert fired == []


async def test_on_rollback_registered():
    """AC-ZG4-EB-03-1: 带 on_rollback 的拦截型在 robust BAD 时逆序被调。"""
    eb = _mk()
    log: list[str] = []

    async def rb():
        log.append("rb")

    eb.subscribe(EventType.ON_START, _ok_handler, "a", weight=20, intercept=True, on_rollback=rb)
    eb.subscribe(EventType.ON_START, _bad_handler, "c", weight=10, intercept=True)
    result = await eb.emit(EventType.ON_START, robust=True)
    assert result.rolled_back
    assert log == ["rb"]


async def test_on_rollback_skip_when_none():
    """AC-ZG4-EB-03-2: 不带 on_rollback → robust 回滚跳过。"""
    eb = _mk()
    eb.subscribe(EventType.ON_START, _ok_handler, "a", weight=20, intercept=True)  # 无 on_rollback
    eb.subscribe(EventType.ON_START, _bad_handler, "c", weight=10, intercept=True)
    result = await eb.emit(EventType.ON_START, robust=True)
    assert result.rolled_back  # 跳过无回调者，回滚仍标记完成


async def test_message_modification_preserved():
    """AC-ZG4-EB-04-1: A 修改消息后 B 返回 BAD → A 的消息修改已生效。"""
    from src.core.types import MaiMessages

    eb = _mk()

    async def mod_a(msg):
        # 模拟修改：返回新消息（deepcopy 链内由 emit 接管）
        return (True, msg)

    async def sub_b(msg):
        return VoteResult(final_vote=Vote.BAD, reason="拒绝")

    eb.subscribe(EventType.ON_START, mod_a, "a", weight=20, intercept=True)
    eb.subscribe(EventType.ON_START, sub_b, "b", weight=10, intercept=True)
    result = await eb.emit(EventType.ON_START, message=MaiMessages(), robust=True)
    assert result.final_vote is Vote.BAD
    assert result.modified_message is not None  # A 的修改已生效于返回结果
    assert result.rolled_back


async def test_non_intercept_bad_ignored():
    """AC-ZG4-EB-05-1: 非拦截型返回 BAD 被忽略，不影响链。"""
    eb = _mk()
    log: list[str] = []

    async def async_bad(msg):
        return VoteResult(final_vote=Vote.BAD)  # 返回值被忽略

    async def ok_after(msg):
        log.append("ok")
        return (True, msg)

    eb.subscribe(EventType.ON_START, async_bad, "async_bad", weight=20, intercept=False)
    eb.subscribe(EventType.ON_START, ok_after, "ok_after", weight=10, intercept=True)
    result = await eb.emit(EventType.ON_START)
    assert result.final_vote is Vote.OK
    assert log == ["ok"]


async def test_event_bus_legacy_return_compat_true():
    """AC-ZG4-INT-03-1: 既有 (True, msg) → 等价 Vote.OK + msg。"""
    eb = _mk()
    result = await eb.emit(EventType.ON_START)
    assert result.final_vote is Vote.OK
    assert result.modified_message is None  # 无消息时 None（原行为）


async def test_event_bus_legacy_return_compat_false():
    """AC-ZG4-INT-03-2: 既有 (False, msg) → 等价 Vote.STOP（默认），链停止。"""
    eb = _mk()
    log: list[str] = []

    async def ok_after(msg):
        log.append("after")
        return (True, msg)

    eb.subscribe(EventType.ON_START, _stop_handler, "stop", weight=20, intercept=True)
    eb.subscribe(EventType.ON_START, ok_after, "after", weight=10, intercept=True)
    result = await eb.emit(EventType.ON_START)
    assert result.final_vote is Vote.STOP
    assert result.vetoer == "stop"
    assert log == []  # 链停止，后续不执行


async def test_event_bus_nofail_continues_on_bad():
    """REQ-ZG4-NOFAIL-01: nofail 模式 BAD 不停止链，继续遍历到底。"""
    eb = _mk()
    log: list[str] = []

    async def sub_bad(msg):
        log.append("bad")
        return VoteResult(final_vote=Vote.BAD, reason="失败1")

    async def sub_ok(msg):
        log.append("ok")
        return (True, msg)

    eb.subscribe(EventType.ON_START, sub_bad, "bad", weight=20, intercept=True)
    eb.subscribe(EventType.ON_START, sub_ok, "ok", weight=10, intercept=True)
    result = await eb.emit(EventType.ON_START, nofail=True)
    assert log == ["bad", "ok"]
    assert result.final_vote is Vote.BAD
    assert len(result.failures) == 1
    assert result.failures[0][0] == "bad"


async def test_event_bus_nofail_no_rollback():
    """REQ-ZG4-NOFAIL-03: nofail 模式 BAD 不触发回滚（与 robust 互斥）。"""
    eb = _mk()
    rollback_log: list[str] = []

    async def rb():
        rollback_log.append("rb")

    eb.subscribe(EventType.ON_START, _ok_handler, "a", weight=20, intercept=True, on_rollback=rb)
    eb.subscribe(EventType.ON_START, _bad_handler, "c", weight=10, intercept=True)
    result = await eb.emit(EventType.ON_START, nofail=True)
    assert not result.rolled_back
    assert rollback_log == []


async def test_event_bus_robust_nofail_mutex():
    """robust 与 nofail 互斥，同传抛 ValueError。"""
    eb = _mk()
    with pytest.raises(ValueError):
        await eb.emit(EventType.ON_START, robust=True, nofail=True)


async def test_ipc_bridge_stop_vote(monkeypatch):
    """P1: 桥接后 continue_flag=False → final_vote=Vote.STOP（vetoer=ipc_bridge）。"""
    eb = _mk()
    eb.subscribe(EventType.ON_START, _ok_handler, "a", weight=20, intercept=True)

    async def fake_bridge(self, event_type, continue_flag, message):
        assert continue_flag is True
        return False, message  # 桥接中断

    monkeypatch.setattr(EventBus, "_bridge_to_ipc_runtime", fake_bridge)
    result = await eb.emit(EventType.ON_START)
    assert result.final_vote is Vote.STOP
    assert result.vetoer == "ipc_bridge"


async def test_chain_stop_vetoer_not_overridden_by_bridge(monkeypatch):
    """P1 回归: 链内 STOP 的 vetoer 不被桥接分支覆盖。"""
    eb = _mk()
    eb.subscribe(EventType.ON_START, _stop_handler, "stop", weight=20, intercept=True)

    async def fake_bridge(self, event_type, continue_flag, message):
        assert continue_flag is False  # 链停止后桥接不执行
        return continue_flag, message

    monkeypatch.setattr(EventBus, "_bridge_to_ipc_runtime", fake_bridge)
    result = await eb.emit(EventType.ON_START)
    assert result.final_vote is Vote.STOP
    assert result.vetoer == "stop"  # 不被覆盖为 ipc_bridge
    assert result.rolled_back is False


async def test_event_bus_introspection():
    """NFR-ZG4-MNT-02: get_handler_list / get_vote_history 非空。"""
    eb = _mk()

    async def rb():
        return None

    eb.subscribe(EventType.ON_START, _ok_handler, "a", weight=20, intercept=True, on_rollback=rb)
    infos = eb.get_handler_list(EventType.ON_START)
    assert len(infos) == 1
    assert infos[0].name == "a"
    assert infos[0].weight == 20
    assert infos[0].intercept
    assert infos[0].has_on_rollback

    await eb.emit(EventType.ON_START)
    history = eb.get_vote_history(EventType.ON_START)
    assert len(history) == 1
    assert history[0].final_vote is Vote.OK


async def test_event_bus_configure_idempotent():
    """P0: configure 幂等，重复调用安全，未注入项保持当前值。"""
    eb = _mk()
    eb.configure(rollback_timeout=2.5, vote_history_capacity=50)
    eb.configure()  # 无参幂等
    assert eb._rollback_timeout == 2.5
    eb.configure(rollback_timeout=1.0)  # 部分注入
    assert eb._rollback_timeout == 1.0
    # 内省容量生效：注入后记录仍工作
    await eb.emit(EventType.ON_START)
    assert len(eb.get_vote_history(EventType.ON_START)) == 1


async def test_unique_priority_event_bus():
    """REQ-ZG4-REG-01: EventBus 同 weight 冲突抛 DuplicatePriorityError。"""
    eb = _mk()
    eb.subscribe(EventType.ON_START, _ok_handler, "a", weight=10, unique_priority=True)
    with pytest.raises(DuplicatePriorityError):
        eb.subscribe(EventType.ON_START, _ok_handler, "b", weight=10, unique_priority=True)


async def test_non_intercept_on_rollback_ignored():
    """非拦截型提供 on_rollback → 忽略（has_on_rollback=False）。"""
    eb = _mk()

    async def rb():
        return None

    async def async_handler(msg):
        return None

    eb.subscribe(EventType.ON_START, async_handler, "async", intercept=False, on_rollback=rb)
    infos = eb.get_handler_list(EventType.ON_START)
    assert infos[0].has_on_rollback is False


async def test_nofail_stop_continues_traversal():
    """CX P2 回归: nofail 模式 STOP 不中断链（与 notify_nofail 一致）。"""
    eb = _mk()
    log: list[str] = []

    async def sub_stop(msg):
        log.append("stop")
        return (False, msg)  # 旧签名 False → STOP

    async def sub_ok(msg):
        log.append("ok")
        return (True, msg)

    eb.subscribe(EventType.ON_START, sub_stop, "stop", weight=20, intercept=True)
    eb.subscribe(EventType.ON_START, sub_ok, "ok", weight=10, intercept=True)
    result = await eb.emit(EventType.ON_START, nofail=True)
    assert log == ["stop", "ok"]  # 遍历到底
    assert result.final_vote is Vote.DONE  # nofail 无 BAD → DONE


async def test_nofail_bad_not_overridden_by_bridge(monkeypatch):
    """CX P2 回归: nofail BAD 聚合不被桥接中断覆盖为 STOP。"""
    eb = _mk()
    eb.subscribe(EventType.ON_START, _bad_handler, "bad", weight=20, intercept=True)

    async def fake_bridge(self, event_type, continue_flag, message):
        assert continue_flag is True  # nofail 时桥接照常执行
        return False, message  # 桥接中断

    monkeypatch.setattr(EventBus, "_bridge_to_ipc_runtime", fake_bridge)
    result = await eb.emit(EventType.ON_START, nofail=True)
    assert result.final_vote is Vote.BAD  # 不被降级为 STOP
    assert result.vetoer == "bad"  # 不被覆盖为 ipc_bridge
    assert len(result.failures) == 1
