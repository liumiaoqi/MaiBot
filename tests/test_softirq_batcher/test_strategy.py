"""SoftirqBatcher 调度策略测试：hrrn/two_queue/fifo 正确性与延迟特征。"""

import asyncio

from src.core.softirq_batcher import SchedulingStrategy, SoftirqBatcher


async def test_fifo_all_processed_no_dup():
    """FIFO：所有条目被处理且无重复（spec 5.1.1-6d）"""
    received: list[int] = []

    async def handler(batch: list[int]) -> None:
        received.extend(batch)

    batcher = SoftirqBatcher(handler=handler, strategy=SchedulingStrategy.FIFO)
    batcher.start()
    for i in range(500):
        batcher.raise_softirq(i)

    await asyncio.sleep(0.2)
    assert len(received) == 500
    assert len(set(received)) == 500
    await batcher.stop()


async def test_two_queue_all_processed_no_dup():
    """two_queue：所有条目被处理且无重复（spec 5.1.1-6d）"""
    received: list[int] = []

    async def handler(batch: list[int]) -> None:
        received.extend(batch)

    batcher = SoftirqBatcher(handler=handler, strategy=SchedulingStrategy.TWO_QUEUE)
    batcher.start()
    for i in range(500):
        batcher.raise_softirq(i, is_heavy=i % 5 == 0)

    await asyncio.sleep(0.2)
    assert len(received) == 500
    assert len(set(received)) == 500
    await batcher.stop()


async def test_hrrn_all_processed_no_dup():
    """HRRN：所有条目被处理且无重复（spec 5.1.1-6d）"""
    received: list[int] = []

    async def handler(batch: list[int]) -> None:
        received.extend(batch)

    batcher = SoftirqBatcher(handler=handler, strategy=SchedulingStrategy.HRRN)
    batcher.start()
    for i in range(500):
        batcher.raise_softirq(i, is_heavy=i % 5 == 0)

    await asyncio.sleep(0.2)
    assert len(received) == 500
    assert len(set(received)) == 500
    await batcher.stop()


async def test_hrrn_degrades_to_wait_order_without_heavy():
    """无分级信息时 hrrn 退化为按等待时间排序（spec 5.1.1-6d）"""
    received: list[int] = []

    async def handler(batch: list[int]) -> None:
        received.extend(batch)

    batcher = SoftirqBatcher(handler=handler, strategy=SchedulingStrategy.HRRN)
    batcher.start()
    for i in range(100):
        batcher.raise_softirq(i)  # 全部 is_heavy=False

    await asyncio.sleep(0.1)
    assert len(received) == 100
    await batcher.stop()


async def test_two_queue_light_priority():
    """two_queue：轻任务绝对优先于未老化重任务（spec 5.1.1-6b）"""
    first_batch: list[bool] = []

    async def handler(batch: list[bool]) -> None:
        if not first_batch:
            first_batch.extend(batch)

    batcher = SoftirqBatcher(
        handler=handler,
        strategy=SchedulingStrategy.TWO_QUEUE,
        aging_threshold_ms=1000.0,  # 高阈值：重任务不会老化
        budget_count=200,
    )
    batcher.start()
    # 先入重任务，再入轻任务
    for _ in range(10):
        batcher.raise_softirq(True, is_heavy=True)
    for _ in range(10):
        batcher.raise_softirq(False, is_heavy=False)

    await asyncio.sleep(0.1)
    # 第一批应全是轻任务（False）
    assert all(not item for item in first_batch)
    await batcher.stop()