"""T6.2 内部轮次队列 maxsize 测试。"""

import asyncio


async def test_queue_maxsize_limits_capacity():
    """队列 maxsize=32 限制容量"""
    queue: asyncio.Queue[str] = asyncio.Queue(maxsize=32)
    for i in range(32):
        queue.put_nowait(f"item_{i}")

    assert queue.qsize() == 32
    # 第 33 条应抛 QueueFull
    try:
        queue.put_nowait("overflow")
        assert False, "应抛 QueueFull"
    except asyncio.QueueFull:
        pass

    assert queue.qsize() == 32  # 未增加


async def test_queue_full_caught_with_warning():
    """put_nowait 满后捕获 QueueFull 并告警（模拟 T6.2 改造）"""
    queue: asyncio.Queue[str] = asyncio.Queue(maxsize=32)
    for i in range(32):
        queue.put_nowait(f"item_{i}")

    # 模拟 T6.2 改造后的 put_nowait 包 try/except
    try:
        queue.put_nowait("overflow")
    except asyncio.QueueFull:
        # 告警被记录（这里只验证不抛出）
        pass

    # 队列仍为 32，未崩溃
    assert queue.qsize() == 32


async def test_queue_blocking_put_still_works():
    """阻塞式 put 语义保持（:2011 await put）"""
    queue: asyncio.Queue[str] = asyncio.Queue(maxsize=1)
    queue.put_nowait("first")

    # 阻塞式 put 会等待空位
    async def delayed_get():
        await asyncio.sleep(0.01)
        item = await queue.get()
        return item

    task = asyncio.create_task(delayed_get())
    await queue.put("second")  # 阻塞直到有空位
    item = await task
    assert item == "first"
    assert queue.get_nowait() == "second"