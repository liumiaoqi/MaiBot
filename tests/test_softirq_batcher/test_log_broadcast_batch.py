"""T6.1 日志广播批量化测试：WebSocketLogHandler + SoftirqBatcher。"""

import asyncio
import logging
from unittest.mock import AsyncMock, patch

from src.common.logger import WebSocketLogHandler


async def test_set_loop_constructs_softirq():
    """set_loop 后 SoftirqBatcher 被构造并启动"""
    handler = WebSocketLogHandler()
    loop = asyncio.get_running_loop()
    handler.set_loop(loop)
    assert handler._softirq is not None
    assert handler._softirq._drainer is not None
    handler.close()


async def test_emit_enqueues_to_softirq():
    """emit 后日志入 SoftirqBatcher 队列，不创建逐条 Task"""
    handler = WebSocketLogHandler()
    loop = asyncio.get_running_loop()
    handler.set_loop(loop)

    # 构造一条日志 record
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname=__file__, lineno=1,
        msg="test message", args=None, exc_info=None,
    )

    with patch("asyncio.create_task") as mock_create:
        handler.emit(record)
        assert not mock_create.called  # 不创建逐条 Task

    assert handler._softirq.queue_size() >= 1  # 入队了
    handler.close()


async def test_batch_broadcast_executes():
    """批量广播最终执行 broadcast_log"""
    handler = WebSocketLogHandler()
    loop = asyncio.get_running_loop()
    handler.set_loop(loop)

    received: list[dict] = []

    async def mock_broadcast(log_data: dict) -> None:
        received.append(log_data)

    with patch("src.webui.logs_ws.broadcast_log", mock_broadcast):
        for i in range(5):
            record = logging.LogRecord(
                name="test", level=logging.INFO, pathname=__file__, lineno=i,
                msg=f"msg {i}", args=None, exc_info=None,
            )
            handler.emit(record)

        await asyncio.sleep(0.1)
        assert len(received) == 5

    handler.close()


async def test_broadcast_failure_does_not_crash():
    """广播失败不影响日志主链路（单条失败隔离）"""
    handler = WebSocketLogHandler()
    loop = asyncio.get_running_loop()
    handler.set_loop(loop)

    call_count = 0

    async def mock_broadcast(log_data: dict) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("广播失败")

    with patch("src.webui.logs_ws.broadcast_log", mock_broadcast):
        for i in range(3):
            record = logging.LogRecord(
                name="test", level=logging.INFO, pathname=__file__, lineno=i,
                msg=f"msg {i}", args=None, exc_info=None,
            )
            handler.emit(record)

        await asyncio.sleep(0.1)
        assert call_count == 3  # 全部尝试了，第一条失败不影响后续

    handler.close()


async def test_concurrent_emit_from_threads():
    """多线程并发写日志无丢失"""
    import threading

    handler = WebSocketLogHandler()
    loop = asyncio.get_running_loop()
    handler.set_loop(loop)

    received: list[dict] = []
    lock = threading.Lock()

    async def mock_broadcast(log_data: dict) -> None:
        with lock:
            received.append(log_data)

    with patch("src.webui.logs_ws.broadcast_log", mock_broadcast):
        total = 100
        threads_per = 4
        per_thread = total // threads_per

        def producer(start: int) -> None:
            for i in range(start, start + per_thread):
                record = logging.LogRecord(
                    name="test", level=logging.INFO, pathname=__file__, lineno=i,
                    msg=f"msg {i}", args=None, exc_info=None,
                )
                handler.emit(record)

        threads = [threading.Thread(target=producer, args=(t * per_thread,)) for t in range(threads_per)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        await asyncio.sleep(0.5)
        assert len(received) == total  # 无丢失

    handler.close()