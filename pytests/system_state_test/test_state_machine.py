"""状态机核心单元测试（ZG-6 Task 9）。

覆盖：状态枚举有序（AC-STM-01）、初始态（AC-STM-02）、合法/非法迁移
（AC-STM-03）、并发串行化 + 迁移中查询旧态（AC-STM-04）、历史与淘汰
（AC-STM-05）、谓词（AC-ADAPT-03）、幂等关闭（AC-LIFE-02）。
"""

import asyncio

import pytest

from src.core.system_state.state_machine import SystemStateMachine
from src.core.system_state.types import (
    IllegalTransitionError,
    SystemLifecycleState,
    TransitionReason,
    TransitionVote,
)

# 7 条合法迁移（含 W1 BOOTING→DEGRADING）
LEGAL_TRANSITIONS: list[tuple[SystemLifecycleState, TransitionReason, SystemLifecycleState]] = [
    (SystemLifecycleState.BOOTING, TransitionReason.STARTUP_COMPLETE, SystemLifecycleState.READY),
    (SystemLifecycleState.BOOTING, TransitionReason.STARTUP_COMPLETE_DEGRADED, SystemLifecycleState.DEGRADING),
    (SystemLifecycleState.READY, TransitionReason.HEALTH_LEVEL_CHANGE, SystemLifecycleState.DEGRADING),
    (SystemLifecycleState.DEGRADING, TransitionReason.RECOVERY, SystemLifecycleState.READY),
    (SystemLifecycleState.READY, TransitionReason.SHUTDOWN_SIGNAL, SystemLifecycleState.SHUTTING_DOWN),
    (SystemLifecycleState.DEGRADING, TransitionReason.SHUTDOWN_SIGNAL, SystemLifecycleState.SHUTTING_DOWN),
    (SystemLifecycleState.BOOTING, TransitionReason.SHUTDOWN_SIGNAL, SystemLifecycleState.SHUTTING_DOWN),
]


def test_state_enum_order():
    """AC-ZG6-STM-01-1/2: 四状态有序 0-3 + snake_case 序列化。"""
    assert SystemLifecycleState.BOOTING.value == 0
    assert SystemLifecycleState.READY.value == 1
    assert SystemLifecycleState.DEGRADING.value == 2
    assert SystemLifecycleState.SHUTTING_DOWN.value == 3
    assert SystemLifecycleState.BOOTING.snake_case == "booting"
    assert SystemLifecycleState.READY.snake_case == "ready"
    assert SystemLifecycleState.DEGRADING.snake_case == "degrading"
    assert SystemLifecycleState.SHUTTING_DOWN.snake_case == "shutting_down"


async def test_initial_state_booting():
    """AC-ZG6-STM-02-1: 初始态 BOOTING。"""
    sm = SystemStateMachine()
    assert sm.get_state() == SystemLifecycleState.BOOTING
    assert sm.is_booting() is True
    assert sm.is_running_like() is False


async def test_legal_transitions():
    """AC-ZG6-STM-03-1~5: 7 条合法迁移全覆盖（含 W1 降级启动）。"""
    for old, reason, expected in LEGAL_TRANSITIONS:
        sm = SystemStateMachine()
        sm._state = old  # 直接摆位到起始状态
        sm._shutdown_entered = old == SystemLifecycleState.SHUTTING_DOWN
        if reason == TransitionReason.STARTUP_COMPLETE:
            await sm.trigger_startup_complete()
        elif reason == TransitionReason.STARTUP_COMPLETE_DEGRADED:
            await sm.trigger_startup_complete_degraded()
        elif reason == TransitionReason.HEALTH_LEVEL_CHANGE:
            await sm.trigger_health_level_change("degraded")
        elif reason == TransitionReason.RECOVERY:
            await sm.trigger_health_level_change("healthy")
        elif reason == TransitionReason.SHUTDOWN_SIGNAL:
            await sm.trigger_shutdown()
        assert sm.get_state() == expected, f"{old.snake_case} --{reason.value}--> {expected.snake_case}"


async def test_illegal_transition_rejected():
    """AC-ZG6-STM-03-6/7: 非法迁移抛 IllegalTransitionError + 终态不可迁出。"""
    sm = SystemStateMachine()
    # BOOTING 时健康变更被忽略（不迁移、不抛错）
    await sm.trigger_health_level_change("degraded")
    assert sm.is_booting()
    # READY 时重复 STARTUP_COMPLETE 非法
    await sm.trigger_startup_complete()
    with pytest.raises(IllegalTransitionError):
        await sm.trigger_startup_complete()
    # 终态不可迁出：非 SHUTDOWN_SIGNAL 触发抛错；健康变更被生命周期忽略（不迁移不抛）
    await sm.trigger_shutdown()
    assert sm.is_shutting_down()
    with pytest.raises(IllegalTransitionError):
        await sm.trigger_startup_complete()
    await sm.trigger_health_level_change("healthy")  # SHUTTING_DOWN 忽略
    assert sm.is_shutting_down()
    assert len(sm.get_history()) == 2


async def test_health_change_race_no_raise():
    """CX 审查回归：并发健康变更竞态（锁外预检查读到旧状态）不抛 IllegalTransitionError。"""
    sm = SystemStateMachine()
    await sm.trigger_startup_complete()  # READY
    results = await asyncio.gather(
        sm.trigger_health_level_change("degraded"),
        sm.trigger_health_level_change("fault"),
        return_exceptions=True,
    )
    # 锁内判定：第二个看到 DEGRADING 后忽略而非查表误抛
    assert all(r is None for r in results)
    assert sm.is_degrading()
    assert len(sm.get_history()) == 2


async def test_health_level_mapping():
    """AC-ZG6-INT-02 映射: READY+降级→DEGRADING, DEGRADING+恢复→READY, BOOTING 忽略。"""
    sm = SystemStateMachine()
    await sm.trigger_startup_complete()
    # READY + {DEGRADED, FAULT} → HEALTH_LEVEL_CHANGE → DEGRADING
    await sm.trigger_health_level_change("degraded")
    assert sm.is_degrading()
    # DEGRADING + {HEALTHY, RECOVERING} → RECOVERY → READY
    await sm.trigger_health_level_change("healthy")
    assert sm.is_ready()
    await sm.trigger_health_level_change("degraded")
    await sm.trigger_health_level_change("recovering")
    assert sm.is_ready()
    # BOOTING / SHUTTING_DOWN 忽略（不迁移不记录）
    sm2 = SystemStateMachine()
    await sm2.trigger_health_level_change("degraded")
    assert sm2.is_booting()
    assert sm2.get_history() == []


async def test_transition_atomicity():
    """AC-ZG6-STM-04-1: 并发迁移 Lock 串行化——第二个触发看到第一个的迁移结果。"""
    sm = SystemStateMachine()
    events: list[str] = []

    async def sub(old, new, reason):
        events.append(f"enter:{reason.value}")
        await asyncio.sleep(0.05)
        events.append(f"exit:{reason.value}")
        return TransitionVote.DONE

    sm.subscribe(sub)
    results = await asyncio.gather(
        sm.trigger_startup_complete(),  # BOOTING→READY 合法
        sm.trigger_startup_complete(),  # 串行化后从 READY 出发 → 非法（证明锁生效）
        return_exceptions=True,
    )
    # 一个成功一个被拒：若锁未串行化，两个都从 BOOTING 出发双双成功
    assert sum(r is None for r in results) == 1
    assert sum(isinstance(r, IllegalTransitionError) for r in results) == 1
    # 被拒的迁移在通知前就抛错，唯一成功的通知完整无交错
    assert events[0].startswith("enter:")
    assert events[1].startswith("exit:")
    assert len(events) == 2
    assert len(sm.get_history()) == 1
    assert sm.is_ready()


async def test_query_during_transition_returns_old_state():
    """AC-ZG6-STM-04-2: 迁移中（通知阶段）查询返回旧态——先通知后赋值。"""
    sm = SystemStateMachine()
    observed: list[SystemLifecycleState] = []

    async def sub(old, new, reason):
        observed.append(sm.get_state())
        return TransitionVote.DONE

    sm.subscribe(sub)
    await sm.trigger_startup_complete()
    assert observed == [SystemLifecycleState.BOOTING]


async def test_transition_history():
    """AC-ZG6-STM-05-1/2: 历史记录按序 + 超容量淘汰最早。"""
    sm = SystemStateMachine(history_capacity=3)
    await sm.trigger_startup_complete()  # 1: BOOTING→READY
    await sm.trigger_health_level_change("degraded")  # 2: READY→DEGRADING
    await sm.trigger_health_level_change("healthy")  # 3: DEGRADING→READY
    await sm.trigger_health_level_change("degraded")  # 4: READY→DEGRADING
    history = sm.get_history()
    assert len(history) == 3  # 淘汰最早的 1 条
    assert history[0].old_state == SystemLifecycleState.READY
    assert history[0].new_state == SystemLifecycleState.DEGRADING
    assert history[-1].new_state == SystemLifecycleState.DEGRADING
    # 字段齐全
    for record in history:
        assert record.old_state != record.new_state
        assert record.reason is not None
        assert record.duration_ms >= 0
        assert record.timestamp > 0


async def test_predicates():
    """AC-ZG6-ADAPT-03-1/2/3: 谓词查询全覆盖。"""
    sm = SystemStateMachine()
    assert sm.is_booting()
    assert not sm.is_ready() and not sm.is_degrading() and not sm.is_shutting_down()
    await sm.trigger_startup_complete()
    assert sm.is_ready() and sm.is_running_like()
    await sm.trigger_health_level_change("degraded")
    assert sm.is_degrading() and sm.is_running_like()
    await sm.trigger_shutdown()
    assert sm.is_shutting_down() and not sm.is_running_like()


async def test_idempotent_shutdown():
    """AC-ZG6-LIFE-02-1/2: 进入 SHUTTING_DOWN 后重复信号静默返回（如 SIGTERM 后又 SIGINT）。"""
    sm = SystemStateMachine()
    reasons: list[str] = []

    async def sub(old, new, reason):
        reasons.append(reason.value)
        return TransitionVote.DONE

    sm.subscribe(sub)
    await sm.trigger_startup_complete()  # 通知 1 次（startup_complete）
    await sm.trigger_shutdown()  # READY→SHUTTING_DOWN，通知 1 次（shutdown_signal）
    await sm.trigger_shutdown()  # 已 SHUTTING_DOWN：幂等静默返回，不抛错
    await sm.trigger_shutdown()  # 重复信号
    assert reasons.count("shutdown_signal") == 1
    assert reasons == ["startup_complete", "shutdown_signal"]
    assert sm.is_shutting_down()
    assert len(sm.get_history()) == 2  # BOOTING→READY + READY→SHUTTING_DOWN


async def test_shutdown_history_export(tmp_path, monkeypatch):
    """AC-ZG6-LIFE-06 正常关闭导出触发点: 迁移到 SHUTTING_DOWN 时导出 JSONL。"""
    import json

    sm = SystemStateMachine(history_capacity=10)
    await sm.trigger_startup_complete()
    path = tmp_path / "lifecycle_test_export.log.jsonl"
    monkeypatch.setattr(sm._history, "default_export_path", lambda: path)
    await sm.trigger_shutdown()
    assert path.exists()
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["old_state"] == "booting"
    assert first["new_state"] == "ready"
    last = json.loads(lines[-1])
    assert last["new_state"] == "shutting_down"
