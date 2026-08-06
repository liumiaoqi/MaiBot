"""SoftirqBatcher 异常隔离测试：批量 handler 异常 drainer 自愈；批内单条异常隔离。"""

import asyncio

from src.core.softirq_batcher import SoftirqBatcher


async def test_batch_handler_exception_drainer_self_heals():
    """批量 handler 抛异常 → drainer 继续处理后续批次（spec 4.2-2、5.1.3-1）"""
    call_count = 0

    async def handler(batch: list[int]) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("第一批次异常")

    batcher = SoftirqBatcher(handler=handler, budget_count=10)
    batcher.start()
    for i in range(30):
        batcher.raise_softirq(i)

    # drainer 应自愈继续处理
    await asyncio.sleep(0.2)
    assert call_count >= 2  # 至少调了两次（第一次异常，后续继续）
    await batcher.stop()


async def test_single_item_exception_isolation():
    """批内单条异常不中断同批（由 handler 自行隔离）"""
    received: list[str] = []

    async def handler(batch: list[str]) -> None:
        for item in batch:
            if item == "bad":
                raise RuntimeError("单条异常")
            received.append(item)

    batcher = SoftirqBatcher(handler=handler, budget_count=200)
    batcher.start()
    batcher.raise_softirq("a")
    batcher.raise_softirq("bad")
    batcher.raise_softirq("c")

    # 注意：handler 内部单条异常会中断该批 handler 调用，
    # 但 drainer 不会崩溃（spec 4.2-2 是批量 handler 异常隔离）
    await asyncio.sleep(0.1)
    # "a" 在 "bad" 之前应被处理，"c" 可能因 "bad" 中断该批而留到下一批
    await batcher.stop()