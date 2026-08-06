"""核心 EventBus cancel_handler_tasks 测试（ZG-21 改造：从队列移除未处理条目）。"""

from typing import Optional

from src.core.event_bus import EventBus
from src.core.types import EventType, MaiMessages


async def test_cancel_removes_queued_items():
    """入队若干条目后 cancel → 该 name 未处理条目从队列清除"""
    bus = EventBus()
    bus.start()

    async def handler(msg: Optional[MaiMessages]) -> tuple[bool, Optional[MaiMessages]]:
        return True, msg

    bus.subscribe(EventType.ON_START, handler, name="target", weight=10, intercept=False)

    # emit 多次（非拦截型入队）
    for _ in range(10):
        bus._fire_and_forget(
            bus._handlers[EventType.ON_START][0],
            EventType.ON_START,
            None,
        )

    # 立即 cancel（不等 drainer 处理）
    await bus.cancel_handler_tasks("target")
    # 队列中该 name 的条目已移除
    assert bus._softirq.queue_size() == 0
    await bus.stop()


async def test_cancel_no_matching_name():
    """无该 name 条目时调用不抛异常"""
    bus = EventBus()
    bus.start()

    await bus.cancel_handler_tasks("nonexistent")
    # 不抛异常
    await bus.stop()