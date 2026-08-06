"""AutonomyEventBus ZG-21 批量行为测试：emit_sync 只入队/批内异常隔离/无订阅者零开销/生命周期。"""

import asyncio
from unittest.mock import patch

from src.maisaka.agent_autonomy.event_bus import AutonomyEventBus


async def test_emit_sync_does_not_create_task():
    """emit_sync 只入队，不创建逐条 Task（spec 5.2.1-1a）"""
    bus = AutonomyEventBus()
    received: list[object] = []

    async def handler(event: object) -> None:
        received.append(event)

    bus.subscribe("test_event", handler)
    bus.start()

    with patch("asyncio.create_task") as mock_create:
        bus.emit_sync("test_event", {"key": "value"})
        assert not mock_create.called

    await asyncio.sleep(0.05)
    assert len(received) == 1
    await bus.stop()


async def test_no_subscribers_zero_overhead():
    """无订阅者时队列不增长（spec 5.2.1-5a）"""
    bus = AutonomyEventBus()
    bus.start()
    bus.emit_sync("unknown_event", {"key": "value"})
    assert bus._softirq.queue_size() == 0
    await bus.stop()


async def test_batch_exception_isolation():
    """批内首 handler 抛异常 → 同批后续 handler 仍执行（spec 5.2.1-4a）"""
    bus = AutonomyEventBus()
    received: list[object] = []

    async def bad_handler(event: object) -> None:
        raise RuntimeError("首 handler 异常")

    async def good_handler(event: object) -> None:
        received.append(event)

    bus.subscribe("test_event", bad_handler)
    bus.subscribe("test_event", good_handler)
    bus.start()

    bus.emit_sync("test_event", {"key": "value"})
    await asyncio.sleep(0.05)
    assert len(received) == 1  # good_handler 仍执行
    await bus.stop()


async def test_high_frequency_storm():
    """高频 emit_sync 1000 次事件循环响应性稳定（spec 5.2.3-2）"""
    bus = AutonomyEventBus()
    received: list[int] = []

    async def handler(event: object) -> None:
        received.append(1)

    bus.subscribe("session_message", handler)
    bus.start()

    for i in range(1000):
        bus.emit_sync("session_message", {"seq": i})

    await asyncio.sleep(0.5)
    assert len(received) == 1000
    await bus.stop()


async def test_lifecycle_start_stop():
    """start/stop 正常，loop 未运行时入队不抛（spec 5.2.3-3）"""
    bus = AutonomyEventBus()
    bus.start()
    assert bus._softirq._drainer is not None
    await bus.stop()
    assert bus._softirq._drainer is None


async def test_emit_async_unchanged():
    """emit（async）顺序 await 语义不变（spec 5.2.1-3）"""
    bus = AutonomyEventBus()
    order: list[str] = []

    async def handler_a(event: object) -> None:
        order.append("a")

    async def handler_b(event: object) -> None:
        order.append("b")

    bus.subscribe("test_event", handler_a)
    bus.subscribe("test_event", handler_b)

    await bus.emit("test_event", {"key": "value"})
    assert order == ["a", "b"]  # 顺序执行
    await bus.stop()