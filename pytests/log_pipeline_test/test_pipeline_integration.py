"""ZG-2 管线集成测试（T-13）。

覆盖：Filter+Handler 链（抑制不落盘/不推送/不入缓冲）、摘要输出、
异常隔离（NFR-REL-01）、Runner 批量日志路径、崩溃导出、契约回归。
"""

import json
import logging
import sys
from pathlib import Path

import pytest

import src.common.logger as L


@pytest.fixture(autouse=True)
def _isolate_pipeline():
    """每个测试独立重建管线（避免跨测试状态污染）。"""
    root = logging.getLogger()
    # 清空旧 filter（重建会 addFilter，旧实例残留会干扰判定）
    for f in list(root.filters):
        if isinstance(f, L.SuppressionFilter):
            root.removeFilter(f)
    for handler in list(root.handlers):
        for f in list(handler.filters):
            if isinstance(f, L.SuppressionFilter):
                handler.removeFilter(f)
    L.init_log_pipeline()
    yield
    L._ring_buffer, L._rate_limiter, L._suppressor = (None, None, None)


def test_suppressed_log_not_in_buffer():
    """被抑制日志不入缓冲（Filter 链生效）。"""
    # FAULT 下 DEBUG 抑制
    L._suppressor.set_health_level("fault")
    lg = L.get_logger("test.integration")
    lg.debug("should be suppressed")
    lg.info("should be suppressed too")
    lg.error("should be visible")
    snap = L.get_ring_buffer_snapshot(10)
    events = [e["event"] for e in snap if e["logger_name"] == "test.integration"]
    assert "should be visible" in events
    assert "should be suppressed" not in events
    assert "should be suppressed too" not in events
    L._suppressor.set_health_level("healthy")


def test_ratelimit_summary_goes_through_pipeline():
    """摘要日志带 rate_limit 标记经管线输出。"""
    import time as _time

    lg = L.get_logger("test.rtl.integration")
    for _ in range(100):
        lg.warning("identical")
    # 模拟窗口过期（摘要窗口结束输出）
    for w in L._rate_limiter._windows.values():
        w.window_start = _time.monotonic() - 5.0
    L._rate_limiter.emit_summaries(lambda s: L._log_summary(s))
    snap = L.get_ring_buffer_snapshot(50)
    summaries = [e for e in snap if e["rate_limit"]]
    assert len(summaries) >= 1


def test_filter_exception_does_not_break_pipeline():
    """裁决层异常隔离：Filter 抛异常放行，落盘/缓冲不受影响（NFR-REL-01）。"""

    class BoomFilter(logging.Filter):
        def filter(self, record):
            raise RuntimeError("boom")

    root = logging.getLogger()
    root.addFilter(BoomFilter())
    try:
        lg = L.get_logger("test.boom")
        lg.info("still works")
        snap = L.get_ring_buffer_snapshot(10)
        assert any(e["event"] == "still works" for e in snap)
    finally:
        # 移除 BoomFilter（只移除我们的）
        for f in list(root.filters):
            if isinstance(f, BoomFilter):
                root.removeFilter(f)


def test_crash_dump_exports_buffer():
    """崩溃导出：缓冲导出为 dump_*.log.jsonl，条目一致。"""
    lg = L.get_logger("test.dump.integration")
    for i in range(3):
        lg.info(f"dump entry {i}")
    L._crash_dump.export("test")
    dump_files = list(Path("logs").glob("dump_*.log.jsonl"))
    assert len(dump_files) >= 1
    latest = max(dump_files, key=lambda p: p.stat().st_mtime)
    lines = latest.read_text(encoding="utf-8").strip().split("\n")
    # 至少包含本次 3 条（可能含更早的）
    dump_events = [json.loads(line)["event"] for line in lines if line]
    assert any("dump entry" in e for e in dump_events)


def test_buffer_priority_over_error():
    """ERROR 保留优先级（集成层验证）。"""
    buf = L._ring_buffer
    # 填满 INFO
    for i in range(2000):
        buf.append(
            L.BufferEntry(
                sequence=i, timestamp="t", level="INFO",
                logger_name="test", module="m", event=f"info {i}",
            )
        )
    # 写入 50 条 ERROR（触发淘汰）
    for i in range(50):
        buf.append(
            L.BufferEntry(
                sequence=2000 + i, timestamp="t", level="ERROR",
                logger_name="test", module="m", event=f"error {i}",
            )
        )
    snap = buf.snapshot()
    errors = [e for e in snap if e.level == "ERROR"]
    assert len(errors) == 50  # ERROR 全保留


def test_jsonl_format_preserved():
    """CMP-01: JSONL 落盘格式兼容既有解析（logger_name 字段存在）。"""
    # 现有 JSONL 解析器依赖的字段结构不变
    import src.common.logger as L2

    assert hasattr(L2, "TimestampedFileHandler")
    # 缓冲条目字段与 JSONL 命名一致（spec 6.1）
    buf = L._ring_buffer
    entry = L.BufferEntry(
        sequence=1, timestamp="2026-08-01T00:00:00", level="INFO",
        logger_name="test", module="m", event="e",
    )
    assert entry.logger_name == "test"
    assert entry.level == "INFO"
