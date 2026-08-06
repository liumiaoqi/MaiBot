"""ZG-14 T1.9 — StormTracker ONCE 抑制 / 风暴检测 / 风暴恢复测试。"""

from src.core.error_escalation.config import ErrorEscalationConfig
from src.core.error_escalation.storm import StormTracker
from src.core.error_escalation.types import ErrorLevel


class TestOnceSuppression:
    """ONCE 抑制：同一错误源 once=True 仅首次完整响应（spec §5.4.1 规则 1）。"""

    def test_once_first_only_full_response(self) -> None:
        storm = StormTracker(ErrorEscalationConfig())
        fp = "test-source"
        first = storm.check(fp, once=True, level=ErrorLevel.WARN)
        assert first.log_allowed is True
        for _ in range(9):
            decision = storm.check(fp, once=True, level=ErrorLevel.WARN)
            assert decision.log_allowed is False

    def test_once_fired_persists_across_windows(self, fake_clock) -> None:
        """once_fired 进程生命周期内不重置（spec §6.5 字段 4）。"""
        clock = fake_clock
        storm = StormTracker(ErrorEscalationConfig(count_window_sec=10.0), time_func=clock)
        fp = "persistent-source"
        assert storm.check(fp, once=True, level=ErrorLevel.WARN).log_allowed is True
        clock.advance(100.0)  # 跨多个窗口
        assert storm.check(fp, once=True, level=ErrorLevel.WARN).log_allowed is False

    def test_without_once_always_full_response(self) -> None:
        storm = StormTracker(ErrorEscalationConfig())
        fp = "normal-source"
        for _ in range(10):
            assert storm.check(fp, once=False, level=ErrorLevel.WARN).log_allowed is True

    def test_unknown_source_aggregates(self) -> None:
        """指纹 None 按"未知源"聚合（spec §5.4.3 异常场景 1）。"""
        storm = StormTracker(ErrorEscalationConfig())
        assert storm.check(None, once=True, level=ErrorLevel.WARN).log_allowed is True
        assert storm.check(None, once=True, level=ErrorLevel.WARN).log_allowed is False


class TestStormDetection:
    """风暴检测：窗口内次数 ≥ max(阈值×10, storm_min_threshold) 标记风暴源。"""

    def test_storm_marked_at_threshold(self) -> None:
        """storm_min_threshold=3：第 3 次标记，第 4 次起强制 ONCE（静默）。"""
        storm = StormTracker(ErrorEscalationConfig(storm_min_threshold=3))
        fp = "flood-source"
        assert storm.check(fp, once=False, level=ErrorLevel.WARN).is_storm_source is False
        assert storm.check(fp, once=False, level=ErrorLevel.WARN).is_storm_source is False
        third = storm.check(fp, once=False, level=ErrorLevel.WARN)
        assert third.is_storm_source is True
        assert third.log_allowed is True  # 风暴源首次 = force_once 完整响应
        assert third.force_once is True
        for _ in range(5):
            decision = storm.check(fp, once=False, level=ErrorLevel.WARN)
            assert decision.is_storm_source is True
            assert decision.log_allowed is False  # LOG/NOTIFY 抑制

    def test_storm_threshold_zero_still_effective(self) -> None:
        """计数阈值=0 时 storm_min_threshold 仍生效（P2-3 修复）。"""
        storm = StormTracker(ErrorEscalationConfig(warn_error_threshold=0, storm_min_threshold=5))
        fp = "zero-threshold-source"
        for _ in range(4):
            assert storm.check(fp, once=False, level=ErrorLevel.WARN).is_storm_source is False
        assert storm.check(fp, once=False, level=ErrorLevel.WARN).is_storm_source is True

    def test_storm_threshold_times_ten(self) -> None:
        """阈值=10：max(10×10, 100)=100，第 100 次标记（spec §5.4.1 规则 3）。"""
        storm = StormTracker(ErrorEscalationConfig(warn_error_threshold=10, storm_min_threshold=100))
        fp = "x10-source"
        for _ in range(99):
            assert storm.check(fp, once=False, level=ErrorLevel.WARN).is_storm_source is False
        assert storm.check(fp, once=False, level=ErrorLevel.WARN).is_storm_source is True

    def test_level_specific_threshold(self) -> None:
        """风暴阈值按上报等级对应计数阈值计算。"""
        storm = StormTracker(ErrorEscalationConfig(error_critical_threshold=2, storm_min_threshold=1))
        fp = "error-source"
        # ERROR 级：max(2×10, 1)=20
        for _ in range(19):
            assert storm.check(fp, once=False, level=ErrorLevel.ERROR).is_storm_source is False
        assert storm.check(fp, once=False, level=ErrorLevel.ERROR).is_storm_source is True


class TestStormRecovery:
    """风暴恢复：count_window_sec × 3 无新触发自动解除（spec §5.4.1 规则 4）。"""

    def test_storm_recovers_after_three_windows(self, fake_clock) -> None:
        clock = fake_clock
        storm = StormTracker(
            ErrorEscalationConfig(storm_min_threshold=3, count_window_sec=10.0),
            time_func=clock,
        )
        fp = "recovering-source"
        for _ in range(3):
            storm.check(fp, once=False, level=ErrorLevel.WARN)
        assert storm.is_storm_source(fp) is True
        # 3 个窗口（30 秒）无新触发
        clock.advance(35.0)
        decision = storm.check(fp, once=False, level=ErrorLevel.WARN)
        assert decision.is_storm_source is False
        assert decision.log_allowed is True  # 恢复正常完整响应

    def test_storm_does_not_recover_within_three_windows(self, fake_clock) -> None:
        clock = fake_clock
        storm = StormTracker(
            ErrorEscalationConfig(storm_min_threshold=3, count_window_sec=10.0),
            time_func=clock,
        )
        fp = "not-yet-source"
        for _ in range(3):
            storm.check(fp, once=False, level=ErrorLevel.WARN)
        clock.advance(20.0)  # 2 个窗口 < 3 个窗口
        assert storm.check(fp, once=False, level=ErrorLevel.WARN).is_storm_source is True

    def test_window_zero_never_auto_recovers(self, fake_clock) -> None:
        """count_window_sec=0（全局累计）风暴源不自动恢复（设计决策）。"""
        clock = fake_clock
        storm = StormTracker(ErrorEscalationConfig(storm_min_threshold=2, count_window_sec=0.0), time_func=clock)
        fp = "permanent-source"
        storm.check(fp, once=False, level=ErrorLevel.WARN)
        storm.check(fp, once=False, level=ErrorLevel.WARN)
        assert storm.is_storm_source(fp) is True
        clock.advance(100000.0)
        assert storm.is_storm_source(fp) is True  # 永不自动恢复

    def test_explicit_clear_storm(self) -> None:
        """clear_storm 重置窗口状态：解除后不再被残留计数立即触发。"""
        storm = StormTracker(ErrorEscalationConfig(storm_min_threshold=3))
        fp = "clearable-source"
        for _ in range(3):
            storm.check(fp, once=False, level=ErrorLevel.WARN)
        assert storm.is_storm_source(fp) is True
        storm.clear_storm(fp)
        assert storm.is_storm_source(fp) is False
        # 窗口已重置：解除后首次 check 计数 1 < 3，不复发风暴
        assert storm.check(fp, once=False, level=ErrorLevel.WARN).is_storm_source is False
        assert storm.check(fp, once=False, level=ErrorLevel.WARN).log_allowed is True


class TestMarkStorm:
    def test_mark_storm_forces_once(self) -> None:
        storm = StormTracker(ErrorEscalationConfig())
        fp = "manual-marked"
        storm.mark_storm(fp)
        first = storm.check(fp, once=False, level=ErrorLevel.WARN)
        assert first.is_storm_source is True
        assert first.log_allowed is True  # 标记后首次完整响应
        assert storm.check(fp, once=False, level=ErrorLevel.WARN).log_allowed is False
