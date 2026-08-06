"""SoftirqBatcher 生命周期测试：start/stop 语义、幂等、loop 未运行时仅入队。"""

import asyncio

from src.core.softirq_batcher import SoftirqBatcher


async def test_start_idempotent():
    """重复 start 不创建第二个 Task（幂等）"""
    async def handler(batch: list[str]) -> None:
        pass

    batcher = SoftirqBatcher(handler=handler)
    batcher.start()
    drainer1 = batcher._drainer
    batcher.start()
    drainer2 = batcher._drainer
    assert drainer1 is drainer2
    await batcher.stop()


async def test_stop_no_pending_drainer():
    """stop 后无悬挂 drainer Task"""
    async def handler(batch: list[str]) -> None:
        pass

    batcher = SoftirqBatcher(handler=handler)
    batcher.start()
    assert batcher._drainer is not None
    assert not batcher._drainer.done()
    await batcher.stop()
    assert batcher._drainer is None


async def test_stop_does_not_process_backlog():
    """stop 后积压不再处理（spec 5.1.3-2）"""
    received: list[int] = []

    async def handler(batch: list[int]) -> None:
        received.extend(batch)

    batcher = SoftirqBatcher(handler=handler, budget_count=200)
    batcher.start()
    # 入队后立即 stop，不等处理
    for i in range(100):
        batcher.raise_softirq(i)
    await batcher.stop()
    # 积压可能部分处理或全未处理，但 stop 后不再处理
    size_after_stop = batcher.queue_size()
    await asyncio.sleep(0.1)
    assert batcher.queue_size() == size_after_stop  # 不再变化


async def test_raise_without_start_no_crash():
    """drainer 未 start、loop 未运行时调用不抛异常（spec 5.2.3-3）"""
    async def handler(batch: list[str]) -> None:
        pass

    batcher = SoftirqBatcher(handler=handler)
    # 不 start，直接 raise
    batcher.raise_softirq("item1")
    batcher.raise_softirq("item2")
    assert batcher.queue_size() == 2


async def test_stop_then_restart_consumes_backlog():
    """停止→再 start 可重新消费此前滞留条目"""
    received: list[int] = []

    async def handler(batch: list[int]) -> None:
        received.extend(batch)

    batcher = SoftirqBatcher(handler=handler, budget_count=200)
    # 入队但不 start（loop 未运行，仅入队）
    batcher.raise_softirq(1)
    batcher.raise_softirq(2)
    assert batcher.queue_size() == 2

    batcher.start()
    await asyncio.sleep(0.05)
    assert len(received) == 2
    await batcher.stop()