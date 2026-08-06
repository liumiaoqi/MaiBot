"""ZG-14 T1.9 — 性能指标测试（spec §4.1 规则 1/2/4）。

指标：
- 单次 report 同步开销 ≤ 50μs（完整路径含 LOG/TAINT/COUNT + 升级判定）
- ErrorCounter 10000 次 bump < 10ms（无锁快速路径）
- 风暴抑制 1 秒 200 次进入 ONCE（≤ 100 次，spec §4.1 规则 4）
"""

import time
from unittest.mock import MagicMock

import src.core.error_escalation.escalator as escalator_module
from src.core.error_escalation.config import ErrorEscalationConfig
from src.core.error_escalation.counter import ErrorCounter
from src.core.error_escalation.escalator import ErrorEscalator
from src.core.error_escalation.storm import StormTracker
from src.core.error_escalation.types import ErrorLevel

_REPORT_BUDGET_US = 50
_BUMP_BUDGET_MS = 10
_REPORT_SAMPLE = 200


def test_report_sync_overhead_within_budget() -> None:
    """单次 report 同步开销 ≤ 50μs（spec §4.1 规则 1）。

    完整路径：等级判定 + 开关/计数升级检查 + 风暴抑制 + LOG + TAINT +
    异步动作派发（create_task 不 await）。无运行中 loop 时异步动作跳过，
    同步段不受影响。
    """
    esc = ErrorEscalator(ErrorEscalationConfig())
    esc.set_taint_mask_port(MagicMock())
    # LOG 走 mock logger：日志 I/O（handler 输出）属 ZG-2 日志管线域，
    # 本测试测引擎同步路径（等级判定 + 计数 + 风暴 + TAINT + 派发）
    original_logger = escalator_module.logger
    escalator_module.logger = MagicMock()
    try:
        _measure_report(esc)
    finally:
        escalator_module.logger = original_logger


def _measure_report(esc: ErrorEscalator) -> None:
    """预热 + 采样（logger 已 mock，测纯引擎同步开销）。"""
    esc.report(ErrorLevel.WARN, "warmup")
    start = time.perf_counter_ns()
    for i in range(_REPORT_SAMPLE):
        esc.report(ErrorLevel.WARN, f"perf sample {i}")
    elapsed_us = (time.perf_counter_ns() - start) / _REPORT_SAMPLE / 1000
    assert elapsed_us <= _REPORT_BUDGET_US, f"report 同步开销 {elapsed_us:.1f}μs 超预算 50μs"


def test_counter_10000_bumps_fast() -> None:
    """ErrorCounter 10000 次 bump < 10ms（spec §4.1 规则 2 无锁快速路径）。"""
    counter = ErrorCounter(ErrorEscalationConfig(warn_error_threshold=100000))
    start = time.perf_counter_ns()
    for _ in range(10000):
        counter.bump(ErrorLevel.WARN)
    elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000
    assert elapsed_ms < _BUMP_BUDGET_MS, f"10000 次 bump {elapsed_ms:.2f}ms 超预算 10ms"
    assert counter.get_count(ErrorLevel.WARN) == 10000


def test_storm_enters_once_within_100_reports() -> None:
    """风暴抑制 1 秒 200 次进入 ONCE，第 101 次起静默（spec §4.1 规则 4）。

    默认 storm_min_threshold=100："超过 100 次"进入 ONCE——第 100 次
    恰好达阈标记风暴源（force_once 完整响应），第 101 次起静默。
    """
    storm = StormTracker(ErrorEscalationConfig())
    fp = "perf-flood"
    first_silent_at = None
    for i in range(200):
        decision = storm.check(fp, once=False, level=ErrorLevel.WARN)
        if not decision.log_allowed and first_silent_at is None:
            first_silent_at = i + 1
    assert first_silent_at == 101, f"风暴抑制 {first_silent_at} 次才进入，期望第 101 次"
    assert storm.is_storm_source(fp) is True
