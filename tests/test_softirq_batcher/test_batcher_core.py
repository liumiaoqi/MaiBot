"""SoftirqBatcher 核心行为测试：入队/批量执行/queue_size/无订阅者零开销。"""

import asyncio

import pytest

from src.core.softirq_batcher import SchedulingStrategy, SoftirqBatcher


async def test_raise_softirq_enqueues_without_execution():
    """raise_softirq 只入队不执行回调（spec 5.1.1-1a）"""
    received: list[str] = []

    async def handler(batch: list[str]) -> None:
        received.extend(batch)

    batcher = SoftirqBatcher(handler=handler)
    # 不 start，drainer 未运行
    batcher.raise_softirq("item1")
    assert batcher.queue_size() == 1
    assert received == []  # 回调未执行
    await batcher.stop()


async def test_batch_execution_after_start():
    """start 后 drainer 批量执行入队条目"""
    received: list[str] = []

    async def handler(batch: list[str]) -> None:
        received.extend(batch)

    batcher = SoftirqBatcher(handler=handler)
    batcher.start()
    batcher.raise_softirq("a")
    batcher.raise_softirq("b")
    batcher.raise_softirq("c")

    # 等待 drainer 处理
    await asyncio.sleep(0.05)
    assert sorted(received) == ["a", "b", "c"]
    assert batcher.queue_size() == 0
    await batcher.stop()


async def test_queue_size_tracks_pending():
    """queue_size 正确反映积压条目数"""
    received: list[int] = []

    async def handler(batch: list[int]) -> None:
        received.extend(batch)

    batcher = SoftirqBatcher(handler=handler, budget_count=10)
    batcher.start()
    for i in range(50):
        batcher.raise_softirq(i)

    # 部分可能已被处理，但 queue_size + len(received) == 50
    await asyncio.sleep(0.1)
    assert len(received) == 50
    assert batcher.queue_size() == 0
    await batcher.stop()


async def test_no_handlers_zero_overhead():
    """无条目时 queue_size 为 0，handler 不被调用"""
    call_count = 0

    async def handler(batch: list[str]) -> None:
        nonlocal call_count
        call_count += 1

    batcher = SoftirqBatcher(handler=handler)
    batcher.start()
    assert batcher.queue_size() == 0
    await asyncio.sleep(0.01)
    assert call_count == 0
    await batcher.stop()


async def test_default_construction_values():
    """默认构造值为 2.0/200/HRRN（spec 4.4-1）"""
    async def handler(batch: list[str]) -> None:
        pass

    batcher = SoftirqBatcher(handler=handler)
    assert batcher._budget_ms == 2.0
    assert batcher._budget_count == 200
    assert batcher._strategy is SchedulingStrategy.HRRN
    await batcher.stop()


async def test_custom_budget_params():
    """显式传入预算参数生效"""
    async def handler(batch: list[str]) -> None:
        pass

    batcher = SoftirqBatcher(handler=handler, budget_ms=5.0, budget_count=50)
    assert batcher._budget_ms == 5.0
    assert batcher._budget_count == 50
    await batcher.stop()