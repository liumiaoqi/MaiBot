"""核心 EventBus 非拦截型 handler 批量执行测试（ZG-21 改造）。"""

import asyncio
from typing import Optional

from src.core.event_bus import EventBus
from src.core.types import EventType, MaiMessages
from src.core.vote import Vote, VoteResult


async def test_fire_and_forget_eventually_executes():
    """非拦截型 handler 最终执行，emit 不等待完成（spec 5.3.1-1a）"""
    bus = EventBus()
    bus.start()
    received: list[Optional[MaiMessages]] = []

    async def handler(msg: Optional[MaiMessages]) -> tuple[bool, Optional[MaiMessages]]:
        received.append(msg)
        return True, msg

    bus.subscribe(EventType.ON_START, handler, name="async_h", weight=10, intercept=False)

    # emit 应立即返回（不等 handler 完成）
    await bus.emit(EventType.ON_START)
    # handler 由 drainer 异步执行
    await asyncio.sleep(0.05)
    assert len(received) == 1
    await bus.stop()


async def test_no_task_storm():
    """连续 emit 触发大量非拦截型 handler → 无逐条 Task 风暴（spec 5.3.1-1b）"""
    bus = EventBus()
    bus.start()
    received: list[int] = []

    async def handler(msg: Optional[MaiMessages]) -> tuple[bool, Optional[MaiMessages]]:
        received.append(1)
        return True, msg

    bus.subscribe(EventType.ON_START, handler, name="async_h", weight=10, intercept=False)

    for _ in range(500):
        await bus.emit(EventType.ON_START)

    await asyncio.sleep(0.5)
    assert len(received) == 500
    # _running_tasks 已移除，不再有逐条 Task 追踪
    assert not hasattr(bus, "_running_tasks")
    await bus.stop()


async def test_batch_exception_isolation():
    """批中一个非拦截型 handler 抛异常 → 同批其余 handler 仍执行（spec 5.3.3-1）"""
    bus = EventBus()
    bus.start()
    received: list[int] = []

    async def bad_handler(msg: Optional[MaiMessages]) -> tuple[bool, Optional[MaiMessages]]:
        raise RuntimeError("handler 异常")

    async def good_handler(msg: Optional[MaiMessages]) -> tuple[bool, Optional[MaiMessages]]:
        received.append(1)
        return True, msg

    bus.subscribe(EventType.ON_START, bad_handler, name="bad", weight=10, intercept=False)
    bus.subscribe(EventType.ON_START, good_handler, name="good", weight=5, intercept=False)

    await bus.emit(EventType.ON_START)
    await asyncio.sleep(0.05)
    assert len(received) == 1  # good_handler 仍执行
    await bus.stop()


async def test_non_intercept_bad_only_warning():
    """非拦截型返回 BAD → 仅告警、不影响投票（spec 5.3.1-2 边界）"""
    bus = EventBus()
    bus.start()

    async def bad_async(msg: Optional[MaiMessages]) -> VoteResult:
        return VoteResult(final_vote=Vote.BAD)

    bus.subscribe(EventType.ON_START, bad_async, name="bad_async", weight=10, intercept=False)

    result = await bus.emit(EventType.ON_START)
    # 非拦截型 BAD 不影响最终投票
    assert result.final_vote is Vote.OK
    await asyncio.sleep(0.05)
    await bus.stop()