"""RingBuffer 单元测试（ZG-2 T-03）。

覆盖：容量覆盖（AC-BUF-01-1/2）、ERROR 保留优先级（AC-BUF-05-1）、
内存上限平稳（AC-BUF-02-1）、单条截断（AC-BUF-02-2）、并发线程安全、sequence 单调。
"""

import threading

from src.common.log_pipeline.ring_buffer import BufferEntry, RingBuffer


def _entry(seq: int, level: str = "INFO", event: str = "msg", name: str = "test") -> BufferEntry:
    return BufferEntry(
        sequence=seq,
        timestamp="2026-08-01T00:00:00",
        level=level,
        logger_name=name,
        module="test_module",
        event=event,
    )


def test_capacity_keeps_recent_only():
    """AC-BUF-01-1: 产生 2500 条，保留最近 2000 条。"""
    buf = RingBuffer(capacity=2000, max_bytes=10**9, entry_max_bytes=32768)
    for i in range(2500):
        buf.append(_entry(i))
    snap = buf.snapshot()
    assert len(snap) == 2000
    assert snap[0].sequence == 500  # 最早被覆盖
    assert snap[-1].sequence == 2499


def test_configurable_capacity():
    """AC-BUF-01-2: 配置 N=100，产生 150 条保留最近 100 条。"""
    buf = RingBuffer(capacity=100, max_bytes=10**9, entry_max_bytes=32768)
    for i in range(150):
        buf.append(_entry(i))
    snap = buf.snapshot()
    assert len(snap) == 100
    assert snap[0].sequence == 50
    assert snap[-1].sequence == 149


def test_error_priority_preserved():
    """AC-BUF-05-1: 缓冲满且混合写入 ERROR 与 INFO，ERROR 保留数量不低于无保护策略。"""
    buf = RingBuffer(capacity=50, max_bytes=10**9, entry_max_bytes=32768)
    # 先填 40 条 INFO
    for i in range(40):
        buf.append(_entry(i, "INFO"))
    # 再写 10 条 ERROR + 20 条 INFO（触发覆盖）
    for i in range(10):
        buf.append(_entry(100 + i, "ERROR"))
    for i in range(20):
        buf.append(_entry(200 + i, "INFO"))

    snap = buf.snapshot()
    errors = [e for e in snap if e.level == "ERROR"]
    # 无保护策略下 FIFO 会淘汰最早 20 条（含前 10 条 ERROR 中部分）
    # 有保护策略下 ERROR 全部保留（10 条）
    assert len(errors) == 10, f"ERROR 应全保留，实际 {len(errors)}"


def test_error_count_maintained_mixed():
    """ZG-2-L2 修复: error_count 在混合写入/淘汰/覆盖下保持正确。"""
    buf = RingBuffer(capacity=10, max_bytes=10**9, entry_max_bytes=32768)
    for i in range(10):
        buf.append(_entry(i, "INFO"))  # 10 条 INFO，error_count=0
    assert buf._error_count == 0

    for i in range(5):
        buf.append(_entry(100 + i, "ERROR"))  # 淘汰 5 条 INFO，写入 5 ERROR
    assert buf._error_count == 5
    snap = buf.snapshot()
    assert len([e for e in snap if e.level == "ERROR"]) == 5


def test_error_count_all_error_eviction_fast_path():
    """ZG-2-L2 修复: 全 ERROR 满缓冲时 error_count 快速判定（行为不变，无全量扫描）。"""
    buf = RingBuffer(capacity=10, max_bytes=10**9, entry_max_bytes=32768)
    for i in range(10):
        buf.append(_entry(i, "ERROR"))  # 全 ERROR 满
    assert buf._error_count == 10

    # 再写 ERROR：兜底覆盖最旧，error_count 保持 10
    buf.append(_entry(100, "ERROR"))
    assert buf._error_count == 10
    assert buf.size == 10
    # 最旧被覆盖（内部 sequence=0 消失，新条目内部序号 10 存在）
    seqs = [e.sequence for e in buf.snapshot()]
    assert 0 not in seqs and 10 in seqs

    # 混入 INFO：error_count 正确下降（全 ERROR 时兜底覆盖掉 ERROR 换 INFO）
    buf.append(_entry(200, "INFO"))
    assert buf._error_count == 9
    assert buf.size == 10


def test_error_count_reset_on_drain():
    """ZG-2-L2 修复: drain 清空后 error_count 归零。"""
    buf = RingBuffer(capacity=10, max_bytes=10**9, entry_max_bytes=32768)
    for i in range(5):
        buf.append(_entry(i, "ERROR"))
    assert buf._error_count == 5
    buf.drain()
    assert buf._error_count == 0


def test_memory_cap_stable():
    """AC-BUF-02-1: 持续写入 10 万条，内存占用稳定 ≤ 上限。"""
    buf = RingBuffer(capacity=2000, max_bytes=2 * 1024 * 1024, entry_max_bytes=32768)
    for i in range(100_000):
        buf.append(_entry(i, "INFO", event="x" * 100))
    assert buf.total_bytes <= 2 * 1024 * 1024
    assert buf.size <= 2000
    # 占用稳定（不随写入量增长）
    assert buf.total_bytes < 1_000_000  # 远低于上限（100 字符条目 × 2000 条）


def test_oversized_entry_truncated():
    """AC-BUF-02-2: 单条 64KB 截断，条目计数不受影响。"""
    buf = RingBuffer(capacity=100, max_bytes=10**9, entry_max_bytes=32768)
    big_event = "y" * (64 * 1024)  # 64KB
    buf.append(_entry(0, "INFO", event=big_event))
    snap = buf.snapshot()
    assert len(snap) == 1
    assert snap[0].truncated is True
    assert len(snap[0].event) < 64 * 1024


def test_sequence_monotonic():
    """sequence 单调递增，进程内不重复。"""
    buf = RingBuffer(capacity=10, max_bytes=10**9, entry_max_bytes=32768)
    for i in range(25):
        buf.append(_entry(i))
    seqs = [e.sequence for e in buf.snapshot()]
    assert seqs == sorted(seqs)
    assert len(set(seqs)) == len(seqs)


def test_concurrent_append_thread_safe():
    """并发写入线程安全（无异常、条数正确）。"""
    buf = RingBuffer(capacity=500, max_bytes=10**9, entry_max_bytes=32768)
    errors: list[Exception] = []

    def writer(start: int, count: int) -> None:
        try:
            for i in range(count):
                buf.append(_entry(start + i))
        except Exception as e:  # pragma: no cover
            errors.append(e)

    threads = [threading.Thread(target=writer, args=(i * 1000, 1000)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert buf.size == 500
    assert buf._seq == 4000  # 4000 条全部写入过


def test_drain_clears():
    """drain 取出全部并清空。"""
    buf = RingBuffer(capacity=10, max_bytes=10**9, entry_max_bytes=32768)
    for i in range(5):
        buf.append(_entry(i))
    drained = buf.drain()
    assert len(drained) == 5
    assert buf.size == 0
    assert buf.snapshot() == []
