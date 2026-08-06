"""核心 EventBus 拦截型 handler 同步链回归测试（ZG-21 改造后行为不变）。"""

from typing import Optional

from src.core.event_bus import EventBus
from src.core.types import EventType, MaiMessages
from src.core.vote import Vote, VoteResult


async def test_intercept_handler_executes_synchronously():
    """拦截型 handler 同步顺序执行"""
    bus = EventBus()
    bus.start()
    order: list[str] = []

    async def handler_a(msg: Optional[MaiMessages]) -> tuple[bool, Optional[MaiMessages]]:
        order.append("a")
        return True, msg

    async def handler_b(msg: Optional[MaiMessages]) -> tuple[bool, Optional[MaiMessages]]:
        order.append("b")
        return True, msg

    bus.subscribe(EventType.ON_START, handler_a, name="a", weight=10, intercept=True)
    bus.subscribe(EventType.ON_START, handler_b, name="b", weight=5, intercept=True)

    result = await bus.emit(EventType.ON_START)
    assert order == ["a", "b"]  # 按权重顺序
    assert result.final_vote is Vote.OK
    await bus.stop()


async def test_intercept_stop_halts_chain():
    """拦截型 handler 返回 STOP 中止链，非拦截型不 fire"""
    bus = EventBus()
    bus.start()
    intercept_ran = False
    async_ran = False

    async def stop_handler(msg: Optional[MaiMessages]) -> VoteResult:
        nonlocal intercept_ran
        intercept_ran = True
        return VoteResult(final_vote=Vote.STOP)

    async def async_handler(msg: Optional[MaiMessages]) -> tuple[bool, Optional[MaiMessages]]:
        nonlocal async_ran
        async_ran = True
        return True, msg

    bus.subscribe(EventType.ON_START, stop_handler, name="stopper", weight=10, intercept=True)
    bus.subscribe(EventType.ON_START, async_handler, name="async", weight=5, intercept=False)

    result = await bus.emit(EventType.ON_START)
    assert intercept_ran
    assert not async_ran  # 链停止后非拦截型不 fire
    assert result.final_vote is Vote.STOP
    await bus.stop()


async def test_intercept_bad_triggers_rollback():
    """拦截型 handler 返回 BAD + robust 触发逆序回滚"""
    bus = EventBus()
    bus.start()
    rollback_order: list[str] = []

    async def ok_handler(msg: Optional[MaiMessages]) -> tuple[bool, Optional[MaiMessages]]:
        return True, msg

    async def rollback_ok() -> None:
        rollback_order.append("ok_rollback")

    async def bad_handler(msg: Optional[MaiMessages]) -> VoteResult:
        return VoteResult(final_vote=Vote.BAD, reason="test bad")

    bus.subscribe(EventType.ON_START, ok_handler, name="ok", weight=10, intercept=True, on_rollback=rollback_ok)
    bus.subscribe(EventType.ON_START, bad_handler, name="bad", weight=5, intercept=True)

    result = await bus.emit(EventType.ON_START, robust=True)
    assert result.final_vote is Vote.BAD
    assert result.rolled_back
    assert rollback_order == ["ok_rollback"]  # 逆序回滚已执行者
    await bus.stop()


async def test_intercept_not_using_softirq():
    """拦截型路径未接入 SoftirqBatcher（spec 5.3.3-2 禁止项）"""
    bus = EventBus()
    bus.start()

    async def handler(msg: Optional[MaiMessages]) -> tuple[bool, Optional[MaiMessages]]:
        return True, msg

    bus.subscribe(EventType.ON_START, handler, name="intercept", weight=10, intercept=True)

    queue_before = bus._softirq.queue_size()
    await bus.emit(EventType.ON_START)
    queue_after = bus._softirq.queue_size()
    assert queue_before == queue_after == 0  # 拦截型不入队
    await bus.stop()