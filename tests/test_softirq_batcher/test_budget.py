"""SoftirqBatcher 预算约束测试：budget_count 强约束 / budget_ms 软约束。"""

import asyncio

from src.core.softirq_batcher import SoftirqBatcher


async def test_budget_count_limits_batch_size():
    """单批处理条数不超过 budget_count（spec 5.1.1-4a）"""
    batch_sizes: list[int] = []

    async def handler(batch: list[int]) -> None:
        batch_sizes.append(len(batch))

    batcher = SoftirqBatcher(handler=handler, budget_count=50)
    batcher.start()
    for i in range(5000):
        batcher.raise_softirq(i)

    # 等待全部处理完
    await asyncio.sleep(0.5)
    assert sum(batch_sizes) == 5000
    # 每批不超过 50
    assert all(size <= 50 for size in batch_sizes)
    await batcher.stop()


async def test_budget_ms_0_5_functional():
    """budget_ms=0.5 功能正常（spec 5.1.1-3b 参数不敏感）"""
    received: list[int] = []

    async def handler(batch: list[int]) -> None:
        received.extend(batch)

    batcher = SoftirqBatcher(handler=handler, budget_ms=0.5, budget_count=200)
    batcher.start()
    for i in range(100):
        batcher.raise_softirq(i)

    await asyncio.sleep(0.1)
    assert len(received) == 100
    await batcher.stop()


async def test_budget_ms_5_functional():
    """budget_ms=5 功能正常"""
    received: list[int] = []

    async def handler(batch: list[int]) -> None:
        received.extend(batch)

    batcher = SoftirqBatcher(handler=handler, budget_ms=5.0, budget_count=200)
    batcher.start()
    for i in range(100):
        batcher.raise_softirq(i)

    await asyncio.sleep(0.1)
    assert len(received) == 100
    await batcher.stop()


async def test_budget_ms_10_functional():
    """budget_ms=10 功能正常"""
    received: list[int] = []

    async def handler(batch: list[int]) -> None:
        received.extend(batch)

    batcher = SoftirqBatcher(handler=handler, budget_ms=10.0, budget_count=200)
    batcher.start()
    for i in range(100):
        batcher.raise_softirq(i)

    await asyncio.sleep(0.1)
    assert len(received) == 100
    await batcher.stop()