"""SoftirqBatcher 风暴测试：突发大量条目全部处理完成不丢失。"""

import asyncio

from src.core.softirq_batcher import SoftirqBatcher


async def test_storm_20000_all_processed():
    """突发 20000 条 → 多轮清空、全部执行、无丢失（spec 4.2-1、5.1.1-5a）"""
    received: list[int] = []

    async def handler(batch: list[int]) -> None:
        received.extend(batch)

    batcher = SoftirqBatcher(handler=handler, budget_count=200)
    batcher.start()
    for i in range(20000):
        batcher.raise_softirq(i)

    # 等待全部处理完（20000 条 / 200 per batch = 100 轮，每轮约 2ms）
    await asyncio.sleep(1.0)
    assert len(received) == 20000
    assert batcher.queue_size() == 0
    # 无重复
    assert len(set(received)) == 20000
    await batcher.stop()