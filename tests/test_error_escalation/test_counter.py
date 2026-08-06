"""ZG-14 T1.9 — ErrorCounter 计数升级 / 窗口归零 / 阈值禁用测试。"""

import threading

from src.core.error_escalation.config import ErrorEscalationConfig
from src.core.error_escalation.counter import ErrorCounter
from src.core.error_escalation.types import ErrorLevel


class TestThresholdUpgrade:
    """计数升级判定（spec §5.2.1 规则 3/7/11）。"""

    def test_check_threshold_no_increment(self) -> None:
        """check 不递增——升级判定与递增分离（P0-2）。"""
        counter = ErrorCounter(ErrorEscalationConfig(warn_error_threshold=10))
        counter.increment(ErrorLevel.WARN)  # 第 1 次
        assert counter.check_threshold(ErrorLevel.WARN) is None
        assert counter.get_count(ErrorLevel.WARN) == 1  # check 未递增

    def test_tenth_warn_upgrades(self) -> None:
        """warn_error_threshold=10，第 10 次升级 ERROR（spec §5.2.1 规则 3）。"""
        counter = ErrorCounter(ErrorEscalationConfig(warn_error_threshold=10))
        for _ in range(9):
            counter.increment(ErrorLevel.WARN)
        # 第 10 次：历史 9 + 本次 1 = 10 → 达阈
        assert counter.check_threshold(ErrorLevel.WARN) is ErrorLevel.ERROR

    def test_bump_upgrades_on_tenth(self) -> None:
        """bump 单次调用语义：第 10 次返回 ERROR。"""
        counter = ErrorCounter(ErrorEscalationConfig(warn_error_threshold=10))
        for _ in range(9):
            assert counter.bump(ErrorLevel.WARN) is None
        assert counter.bump(ErrorLevel.WARN) is ErrorLevel.ERROR
        assert counter.get_count(ErrorLevel.WARN) == 10

    def test_threshold_zero_disabled(self) -> None:
        """阈值=0 禁用计数升级（spec §5.2.1 规则 7）。"""
        counter = ErrorCounter(ErrorEscalationConfig(warn_error_threshold=0))
        for _ in range(100):
            assert counter.bump(ErrorLevel.WARN) is None

    def test_error_critical_threshold(self) -> None:
        counter = ErrorCounter(ErrorEscalationConfig(error_critical_threshold=3))
        assert counter.bump(ErrorLevel.ERROR) is None
        assert counter.bump(ErrorLevel.ERROR) is None
        assert counter.bump(ErrorLevel.ERROR) is ErrorLevel.CRITICAL

    def test_critical_fatal_threshold(self) -> None:
        counter = ErrorCounter(ErrorEscalationConfig(critical_fatal_threshold=2))
        assert counter.bump(ErrorLevel.CRITICAL) is None
        assert counter.bump(ErrorLevel.CRITICAL) is ErrorLevel.FATAL

    def test_fatal_never_upgrades(self) -> None:
        counter = ErrorCounter(ErrorEscalationConfig())
        assert counter.bump(ErrorLevel.FATAL) is None


class TestCountWindow:
    """窗口归零（spec §5.2.1 规则 8，time_func 注入）。"""

    def test_window_rollover_resets_count(self, fake_clock) -> None:
        clock = fake_clock
        counter = ErrorCounter(
            ErrorEscalationConfig(warn_error_threshold=10, count_window_sec=60.0),
            time_func=clock,
        )
        for _ in range(5):
            counter.increment(ErrorLevel.WARN)
        assert counter.get_count(ErrorLevel.WARN) == 5
        # 60 秒后：计数归零，下一次计数为 1
        clock.advance(60.0)
        counter.increment(ErrorLevel.WARN)
        assert counter.get_count(ErrorLevel.WARN) == 1

    def test_within_window_counts_accumulate(self, fake_clock) -> None:
        clock = fake_clock
        counter = ErrorCounter(ErrorEscalationConfig(count_window_sec=60.0), time_func=clock)
        for _ in range(5):
            counter.increment(ErrorLevel.WARN)
        clock.advance(10.0)
        counter.increment(ErrorLevel.WARN)
        assert counter.get_count(ErrorLevel.WARN) == 6

    def test_window_zero_never_resets(self, fake_clock) -> None:
        """count_window_sec=0 全局累计不归零（spec §5.2.1 规则 8）。"""
        clock = fake_clock
        counter = ErrorCounter(ErrorEscalationConfig(count_window_sec=0.0), time_func=clock)
        for _ in range(5):
            counter.increment(ErrorLevel.WARN)
        clock.advance(100000.0)
        counter.increment(ErrorLevel.WARN)
        assert counter.get_count(ErrorLevel.WARN) == 6

    def test_window_rollover_clears_upgrade_progress(self, fake_clock) -> None:
        """窗口归零后升级进度重置（第 10 次跨窗口不升级）。"""
        clock = fake_clock
        counter = ErrorCounter(
            ErrorEscalationConfig(warn_error_threshold=10, count_window_sec=60.0),
            time_func=clock,
        )
        for _ in range(9):
            counter.increment(ErrorLevel.WARN)
        clock.advance(60.0)
        assert counter.check_threshold(ErrorLevel.WARN) is None  # 归零后 0+1=1 < 10

    def test_reset_window(self) -> None:
        counter = ErrorCounter(ErrorEscalationConfig(count_window_sec=60.0))
        counter.increment(ErrorLevel.ERROR)
        counter.reset_window(ErrorLevel.ERROR)
        assert counter.get_count(ErrorLevel.ERROR) == 0


class TestThreadSafety:
    """跨线程兜底（spec §4.1 规则 2 / §5.2.3 异常场景 1）。"""

    def test_thread_safe_counter_accumulates(self) -> None:
        counter = ErrorCounter(ErrorEscalationConfig(), thread_safe=True)
        results: list[int] = []

        def worker() -> None:
            total = 0
            for _ in range(1000):
                counter.increment(ErrorLevel.WARN)
                total += 1
            results.append(total)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert counter.get_count(ErrorLevel.WARN) == 4000

    def test_get_all_counts_returns_copy(self) -> None:
        counter = ErrorCounter(ErrorEscalationConfig())
        counter.increment(ErrorLevel.WARN)
        snapshot = counter.get_all_counts()
        snapshot[ErrorLevel.WARN] = 999
        assert counter.get_count(ErrorLevel.WARN) == 1
