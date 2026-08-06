"""SoftirqBatcher remove_matching 测试：按谓词移除队列中未处理条目。"""

import asyncio

from src.core.softirq_batcher import SoftirqBatcher


async def test_remove_matching_removes_items():
    """入队 10 条后按谓词移除其中 3 条 → 返回 3、queue_size == 7"""
    async def handler(batch: list[int]) -> None:
        pass

    batcher = SoftirqBatcher(handler=handler)
    for i in range(10):
        batcher.raise_softirq(i)

    removed = batcher.remove_matching(lambda item: item.payload < 3)
    assert removed == 3
    assert batcher.queue_size() == 7
    await batcher.stop()


async def test_remove_matching_no_match():
    """谓词无匹配时返回 0、队列不变"""
    async def handler(batch: list[int]) -> None:
        pass

    batcher = SoftirqBatcher(handler=handler)
    for i in range(10):
        batcher.raise_softirq(i)

    removed = batcher.remove_matching(lambda item: item.payload > 100)
    assert removed == 0
    assert batcher.queue_size() == 10
    await batcher.stop()


async def test_remove_matching_preserves_others():
    """移除操作不影响不匹配条目"""
    async def handler(batch: list[int]) -> None:
        pass

    batcher = SoftirqBatcher(handler=handler, budget_count=200)
    # 不 start，避免 drainer 消费导致竞态
    for i in range(20):
        batcher.raise_softirq(i)

    # 移除偶数
    removed = batcher.remove_matching(lambda item: item.payload % 2 == 0)
    assert removed == 10
    assert batcher.queue_size() == 10
    # 剩余全是奇数
    remaining_items = list(batcher._pending)
    assert all(item.payload % 2 == 1 for item in remaining_items)
    await batcher.stop()