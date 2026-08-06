"""SoftirqBatcher 线程安全测试：跨线程并发入队无丢失/重复/崩溃。"""

import asyncio
import threading

from src.core.softirq_batcher import SoftirqBatcher


async def test_concurrent_enqueue_from_threads():
    """线程池并发入队 10000 条 + drainer 并发消费，无丢/重/崩（spec 5.1.1-7、4.2-4）"""
    received: list[int] = []
    lock = threading.Lock()

    async def handler(batch: list[int]) -> None:
        with lock:
            received.extend(batch)

    batcher = SoftirqBatcher(handler=handler, budget_count=200)
    batcher.start()

    total = 10000
    threads_per = 4
    per_thread = total // threads_per

    def producer(start: int) -> None:
        for i in range(start, start + per_thread):
            batcher.raise_softirq(i)

    threads = []
    for t in range(threads_per):
        threads.append(threading.Thread(target=producer, args=(t * per_thread,)))

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # 等待 drainer 处理完
    await asyncio.sleep(1.0)
    assert len(received) == total
    assert len(set(received)) == total  # 无重复
    await batcher.stop()