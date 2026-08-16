"""ZH1-1a 异步摘要队列测试 — asyncio.Queue 消费者模式。

覆盖 spec 5.3.1 规则 1-7：入队不阻塞、深拷贝、队列满丢弃最老、
消费者串行、异常恢复、关闭 flush、未初始化跳过。
"""

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.maisaka.memory.mid_term_summary_queue import (
    MidTermSummaryQueue,
    SummaryBuildSnapshot,
    get_mid_term_summary_queue,
)


def _make_msg(text: str = "测试消息") -> SimpleNamespace:
    """构造 mock LLMContextMessage。"""
    return SimpleNamespace(
        role="user",
        processed_plain_text=text,
        timestamp=asyncio.get_event_loop().time() if False else None,
        mutable_list=[1, 2, 3],
    )


class TestMidTermSummaryQueue:
    """MidTermSummaryQueue 异步队列测试。"""

    def test_queue_init(self) -> None:
        """队列初始化：maxsize + 消费者未启动 + 未关闭。"""
        q = MidTermSummaryQueue(maxsize=100)
        assert q._queue.maxsize == 100
        assert q._consumer_task is None
        assert q._closed is False

    def test_enqueue_not_block(self) -> None:
        """入队不阻塞：耗时 < 5ms（spec 5.3.1 规则 2）。"""
        q = MidTermSummaryQueue(maxsize=100)
        msg = _make_msg("入队测试")
        start = time.perf_counter()
        q.enqueue_summary_build([msg], "sess1")
        elapsed = time.perf_counter() - start
        assert elapsed < 0.005
        assert q._queue.qsize() == 1

    def test_deep_copy_snapshot(self) -> None:
        """深拷贝：入队后修改原消息不影响快照（spec 5.3.1 规则 3）。"""
        q = MidTermSummaryQueue(maxsize=100)
        msg = _make_msg("深拷贝测试")
        original_list = msg.mutable_list
        q.enqueue_summary_build([msg], "sess1")
        snapshot: SummaryBuildSnapshot = q._queue.get_nowait()
        # 修改原消息
        msg.mutable_list.append(999)
        original_list.append(888)
        # 快照不受影响
        assert snapshot.messages[0].mutable_list == [1, 2, 3]
        assert snapshot.messages[0] is not msg

    def test_queue_full_drop_oldest(self) -> None:
        """队列满丢弃最老（spec 5.3.1 规则 4）。"""
        q = MidTermSummaryQueue(maxsize=2)
        q.enqueue_summary_build([_make_msg("msg1")], "sess1")
        q.enqueue_summary_build([_make_msg("msg2")], "sess1")
        assert q._queue.qsize() == 2
        # 第三条入队：满 → 丢弃最老 → 入队新
        q.enqueue_summary_build([_make_msg("msg3")], "sess1")
        assert q._queue.qsize() == 2
        # 最老（msg1）被丢弃，队首是 msg2
        snapshot = q._queue.get_nowait()
        assert snapshot.messages[0].processed_plain_text == "msg2"

    @pytest.mark.asyncio
    async def test_consumer_serial(self) -> None:
        """消费者串行处理（spec 5.3.1 规则 5）。"""
        q = MidTermSummaryQueue(maxsize=100)
        process_mock = AsyncMock()
        with patch.object(q, "_process_snapshot", new=process_mock):
            q.start()
            q.enqueue_summary_build([_make_msg("m1")], "sess1")
            q.enqueue_summary_build([_make_msg("m2")], "sess1")
            await asyncio.sleep(0.1)
            assert process_mock.call_count == 2
            await q.close()

    @pytest.mark.asyncio
    async def test_consumer_exception_recovery(self) -> None:
        """消费者异常恢复：第一条失败不崩溃，第二条仍处理（spec 5.3.1 规则 6）。"""
        q = MidTermSummaryQueue(maxsize=100)
        call_count = 0

        async def _flaky_process(snapshot: SummaryBuildSnapshot) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("第一条处理失败")

        with patch.object(q, "_process_snapshot", new=_flaky_process):
            q.start()
            q.enqueue_summary_build([_make_msg("m1")], "sess1")
            q.enqueue_summary_build([_make_msg("m2")], "sess1")
            await asyncio.sleep(0.15)
            assert call_count == 2  # 两条都被处理
            await q.close()

    @pytest.mark.asyncio
    async def test_close_flush(self) -> None:
        """关闭 flush：close 处理队列剩余条目（spec 5.3.1 规则 7）。"""
        q = MidTermSummaryQueue(maxsize=100)
        process_mock = AsyncMock()
        with patch.object(q, "_process_snapshot", new=process_mock):
            # 不 start 消费者，直接入队
            q.enqueue_summary_build([_make_msg("m1")], "sess1")
            q.enqueue_summary_build([_make_msg("m2")], "sess1")
            await q.close()  # flush 处理剩余
            assert process_mock.call_count == 2
        assert q._closed is True

    @pytest.mark.asyncio
    async def test_close_idempotent(self) -> None:
        """close 幂等：重复调用不报错。"""
        q = MidTermSummaryQueue(maxsize=100)
        with patch.object(q, "_process_snapshot", new=AsyncMock()):
            await q.close()
            await q.close()  # 不报错
        assert q._closed is True

    def test_uninit_enqueue_skip(self) -> None:
        """未初始化入队跳过：get_mid_term_summary_queue() 未 init 返回 None。"""
        # 全局单例未初始化
        with patch("src.maisaka.memory.mid_term_summary_queue._mid_term_summary_queue", None):
            result = get_mid_term_summary_queue()
        assert result is None

    def test_enqueue_snapshot_fields(self) -> None:
        """入队快照字段完整：messages + session_id + enqueued_at。"""
        q = MidTermSummaryQueue(maxsize=100)
        q.enqueue_summary_build([_make_msg("m1")], "sess_fields")
        snapshot = q._queue.get_nowait()
        assert snapshot.session_id == "sess_fields"
        assert len(snapshot.messages) == 1
        assert snapshot.enqueued_at is not None