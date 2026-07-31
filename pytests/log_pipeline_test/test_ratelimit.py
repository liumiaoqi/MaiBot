"""RateLimiter 单元测试（ZG-2 T-04）。

覆盖：同源高频 ≤ 阈值+摘要（AC-RTL-01-1）、多源独立（AC-RTL-01-2）、
白名单逐条（AC-RTL-02-1）、ERROR 豁免（AC-RTL-04-1/2）、摘要字段（AC-RTL-03-1/2）、
monotonic 时钟回拨不锁定。
"""

import logging
import time

import pytest

from src.common.log_pipeline.ratelimit import RateLimiter

APPLY_LEVELS = {logging.DEBUG, logging.INFO, logging.WARNING}


def _record(name: str = "test.module", level: int = logging.WARNING, msg: str = "boom") -> logging.LogRecord:
    return logging.LogRecord(name, level, "path.py", 10, msg, (), None)


def test_same_source_high_frequency_limited():
    """AC-RTL-01-1: 同一模块 1 秒 100 条同签名 WARNING，输出 ≤ 阈值+摘要。"""
    rl = RateLimiter(window_s=1.0, max_events=10, apply_levels=APPLY_LEVELS, whitelist=(), summary_interval_s=1.0)
    allowed = sum(1 for _ in range(100) if rl.check(_record()))
    assert allowed == 10  # 前 10 条放行，其余抑制

    # 模拟窗口过期（设计语义：摘要窗口结束输出）
    for w in rl._windows.values():
        w.window_start = time.monotonic() - 5.0
    summaries: list[dict] = []
    rl.emit_summaries(summaries.append)
    assert len(summaries) == 1
    assert summaries[0]["suppressed_count"] == 90
    assert summaries[0]["actual_count"] == 100
    assert summaries[0]["rate_limit"] is True


def test_multiple_sources_independent():
    """AC-RTL-01-2: 两个不同来源各自高频，抑制按来源独立。"""
    rl = RateLimiter(window_s=1.0, max_events=10, apply_levels=APPLY_LEVELS, whitelist=(), summary_interval_s=1.0)
    allowed_a = sum(1 for _ in range(100) if rl.check(_record(name="mod.a")))
    allowed_b = sum(1 for _ in range(100) if rl.check(_record(name="mod.b")))
    assert allowed_a == 10
    assert allowed_b == 10


def test_whitelist_passthrough():
    """AC-RTL-02-1: 白名单标记的同源高频全部逐条输出。"""
    rl = RateLimiter(window_s=1.0, max_events=10, apply_levels=APPLY_LEVELS, whitelist=("critical.module",), summary_interval_s=1.0)
    allowed = sum(1 for _ in range(100) if rl.check(_record(name="critical.module")))
    assert allowed == 100


def test_error_level_exempt():
    """AC-RTL-04-1/2: ERROR/CRITICAL 同源高频 100 条全部输出且无摘要。"""
    rl = RateLimiter(window_s=1.0, max_events=10, apply_levels=APPLY_LEVELS, whitelist=(), summary_interval_s=1.0)
    allowed_error = sum(1 for _ in range(100) if rl.check(_record(level=logging.ERROR)))
    allowed_critical = sum(1 for _ in range(100) if rl.check(_record(level=logging.CRITICAL)))
    assert allowed_error == 100
    assert allowed_critical == 100

    summaries: list[dict] = []
    rl.emit_summaries(summaries.append)
    assert summaries == []  # 无摘要（未抑制）


def test_summary_fields_match_counts():
    """AC-RTL-03-1/2: 摘要字段与实测一致且带 rate_limit 标记。"""
    rl = RateLimiter(window_s=1.0, max_events=5, apply_levels=APPLY_LEVELS, whitelist=(), summary_interval_s=1.0)
    for _ in range(12):
        rl.check(_record(msg="same event"))
    for w in rl._windows.values():
        w.window_start = time.monotonic() - 5.0
    summaries: list[dict] = []
    rl.emit_summaries(summaries.append)
    assert len(summaries) == 1
    s = summaries[0]
    assert s["actual_count"] == 12
    assert s["suppressed_count"] == 7
    assert s["source"] == "test.module"
    assert s["event"] == "same event"
    assert s["rate_limit"] is True


def test_monotonic_clock_no_lockup():
    """monotonic 时钟回拨不锁定计数（窗口过期自动重置）。"""
    rl = RateLimiter(window_s=1.0, max_events=10, apply_levels=APPLY_LEVELS, whitelist=(), summary_interval_s=1.0)
    # 填满窗口
    for _ in range(10):
        rl.check(_record())
    assert rl.check(_record()) is False  # 抑制

    # 模拟窗口过期：直接操作内部状态（window_start 改为过去）
    for key, w in list(rl._windows.items()):
        w.window_start = time.monotonic() - 5.0

    # 新窗口：放行
    assert rl.check(_record()) is True
