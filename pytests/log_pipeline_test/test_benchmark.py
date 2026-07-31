"""ZG-2 性能基准（T-14，pytest -m benchmark 运行）。

覆盖：缓冲单条附加延迟 <1ms（NFR-PER-01）、抑制判定 <0.1ms（NFR-PER-03）、
持续写入 10 万条内存 ≤2MB（NFR-PER-02）。
"""

import logging
import time

import pytest

from src.common.log_pipeline.ratelimit import RateLimiter
from src.common.log_pipeline.ring_buffer import BufferEntry, RingBuffer


@pytest.mark.benchmark
def test_benchmark_ring_buffer_append_latency():
    """NFR-PER-01: 单条写入附加延迟 < 1ms（均值）。"""
    buf = RingBuffer(capacity=2000, max_bytes=2 * 1024 * 1024, entry_max_bytes=32768)
    entry = BufferEntry(
        sequence=0, timestamp="t", level="INFO",
        logger_name="test", module="m", event="x" * 100,
    )
    # 预热
    for _ in range(100):
        buf.append(entry)
    # 计时 10000 次
    start = time.perf_counter()
    for i in range(10000):
        buf.append(BufferEntry(
            sequence=i, timestamp="t", level="INFO",
            logger_name="test", module="m", event="x" * 100,
        ))
    elapsed = time.perf_counter() - start
    per_entry_ms = elapsed / 10000 * 1000
    print(f"缓冲单条延迟: {per_entry_ms:.4f}ms")
    assert per_entry_ms < 1.0, f"单条延迟 {per_entry_ms:.4f}ms 超过 1ms"


@pytest.mark.benchmark
def test_benchmark_ratelimit_check_latency():
    """NFR-PER-03: 抑制判定单次 < 0.1ms（均值）。"""
    rl = RateLimiter(
        window_s=1.0, max_events=10,
        apply_levels={logging.DEBUG, logging.INFO, logging.WARNING},
        whitelist=(), summary_interval_s=1.0,
    )
    record = logging.LogRecord("test.module", logging.WARNING, "f.py", 1, "event", (), None)
    # 预热
    for _ in range(100):
        rl.check(record)
    # 重新构造（避免窗口状态影响）
    start = time.perf_counter()
    for i in range(10000):
        rec = logging.LogRecord("test.module", logging.WARNING, "f.py", 1, f"event {i}", (), None)
        rl.check(rec)
    elapsed = time.perf_counter() - start
    per_check_ms = elapsed / 10000 * 1000
    print(f"抑制判定延迟: {per_check_ms:.5f}ms")
    assert per_check_ms < 0.1, f"判定延迟 {per_check_ms:.5f}ms 超过 0.1ms"


@pytest.mark.benchmark
def test_benchmark_memory_stable():
    """NFR-PER-02: 持续写入 10 万条内存 ≤ 2MB 无线性增长。"""
    buf = RingBuffer(capacity=2000, max_bytes=2 * 1024 * 1024, entry_max_bytes=32768)
    for i in range(100_000):
        buf.append(BufferEntry(
            sequence=i, timestamp="t", level="INFO",
            logger_name="test", module="m", event="x" * 100,
        ))
    print(f"10 万条后占用: {buf.total_bytes / 1024:.1f}KB（上限 2048KB）")
    assert buf.total_bytes <= 2 * 1024 * 1024
    assert buf.size <= 2000
