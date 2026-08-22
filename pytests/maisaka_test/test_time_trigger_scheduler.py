"""scheduler 单元测试。

覆盖 TimeTriggerScheduler.check_triggers / _is_in_time_range /
_cleanup_cache / reset，以及 TriggerEvent 数据类。
"""

from src.maisaka.agent.config import TimeTriggerRule
from src.maisaka.time_awareness.scheduler import (
    TimeTriggerScheduler,
    TriggerEvent,
)


class TestTriggerEventDataclass:
    """TriggerEvent 数据类测试。"""

    def test_default_timestamp(self):
        event = TriggerEvent(
            trigger_type="greeting",
            rule_index=0,
            message_template="早上好",
        )
        assert event.timestamp > 0

    def test_custom_values(self):
        event = TriggerEvent(
            trigger_type="festival",
            rule_index=2,
            message_template="节日快乐",
            timestamp=1000.0,
        )
        assert event.trigger_type == "festival"
        assert event.rule_index == 2
        assert event.message_template == "节日快乐"
        assert event.timestamp == 1000.0


class TestIsInTimeRange:
    """_is_in_time_range 行为测试。"""

    def setup_method(self):
        self.scheduler = TimeTriggerScheduler()

    def test_in_range(self):
        assert self.scheduler._is_in_time_range("07:00-09:00", 8, 0) is True

    def test_at_start_boundary(self):
        assert self.scheduler._is_in_time_range("07:00-09:00", 7, 0) is True

    def test_at_end_boundary(self):
        assert self.scheduler._is_in_time_range("07:00-09:00", 9, 0) is True

    def test_out_of_range(self):
        assert self.scheduler._is_in_time_range("07:00-09:00", 10, 0) is False

    def test_cross_midnight_range(self):
        # 23:00-02:00 跨午夜
        assert self.scheduler._is_in_time_range("23:00-02:00", 23, 30) is True
        assert self.scheduler._is_in_time_range("23:00-02:00", 1, 0) is True
        assert self.scheduler._is_in_time_range("23:00-02:00", 12, 0) is False

    def test_empty_range_returns_false(self):
        assert self.scheduler._is_in_time_range("", 8, 0) is False

    def test_no_dash_returns_false(self):
        assert self.scheduler._is_in_time_range("0700", 8, 0) is False

    def test_invalid_format_returns_false(self):
        assert self.scheduler._is_in_time_range("abc-def", 8, 0) is False

    def test_hour_only_format(self):
        # 只有小时、无分钟
        assert self.scheduler._is_in_time_range("7-9", 8, 0) is True


class TestCheckTriggers:
    """check_triggers 行为测试。"""

    def test_no_rules_returns_empty(self):
        scheduler = TimeTriggerScheduler()
        result = scheduler.check_triggers([], current_hour=8, current_minute=0)
        assert result == []

    def test_matching_rule_triggers(self):
        scheduler = TimeTriggerScheduler()
        rules = [
            TimeTriggerRule(
                trigger_type="greeting",
                time_range="07:00-09:00",
                message_template="早上好",
            ),
        ]
        result = scheduler.check_triggers(rules, current_hour=8, current_minute=0)
        assert len(result) == 1
        assert result[0].trigger_type == "greeting"
        assert result[0].message_template == "早上好"

    def test_out_of_range_no_trigger(self):
        scheduler = TimeTriggerScheduler()
        rules = [
            TimeTriggerRule(
                trigger_type="greeting",
                time_range="07:00-09:00",
                message_template="早上好",
            ),
        ]
        result = scheduler.check_triggers(rules, current_hour=12, current_minute=0)
        assert result == []

    def test_disabled_rule_skipped(self):
        scheduler = TimeTriggerScheduler()
        rules = [
            TimeTriggerRule(
                trigger_type="greeting",
                time_range="07:00-09:00",
                message_template="早上好",
                enabled=False,
            ),
        ]
        result = scheduler.check_triggers(rules, current_hour=8, current_minute=0)
        assert result == []

    def test_already_fired_not_retriggered(self):
        scheduler = TimeTriggerScheduler()
        rules = [
            TimeTriggerRule(
                trigger_type="greeting",
                time_range="07:00-09:00",
                message_template="早上好",
            ),
        ]
        # 第一次触发
        first = scheduler.check_triggers(rules, current_hour=8, current_minute=0)
        assert len(first) == 1
        # 同一天再次检查不应重复触发
        second = scheduler.check_triggers(rules, current_hour=8, current_minute=30)
        assert second == []

    def test_multiple_rules_some_match(self):
        scheduler = TimeTriggerScheduler()
        rules = [
            TimeTriggerRule(
                trigger_type="morning",
                time_range="07:00-09:00",
                message_template="早上好",
            ),
            TimeTriggerRule(
                trigger_type="evening",
                time_range="18:00-20:00",
                message_template="晚上好",
            ),
        ]
        result = scheduler.check_triggers(rules, current_hour=8, current_minute=0)
        assert len(result) == 1
        assert result[0].trigger_type == "morning"

    def test_rule_index_recorded(self):
        scheduler = TimeTriggerScheduler()
        rules = [
            TimeTriggerRule(
                trigger_type="first",
                time_range="00:00-23:59",
                message_template="a",
                enabled=False,
            ),
            TimeTriggerRule(
                trigger_type="second",
                time_range="00:00-23:59",
                message_template="b",
            ),
        ]
        result = scheduler.check_triggers(rules, current_hour=8, current_minute=0)
        assert len(result) == 1
        # 索引应为 1（跳过 disabled 的 0）
        assert result[0].rule_index == 1


class TestSchedulerReset:
    """reset 行为测试。"""

    def test_reset_clears_fired_cache(self):
        scheduler = TimeTriggerScheduler()
        rules = [
            TimeTriggerRule(
                trigger_type="greeting",
                time_range="07:00-09:00",
                message_template="早上好",
            ),
        ]
        # 触发一次
        scheduler.check_triggers(rules, current_hour=8, current_minute=0)
        # 重置
        scheduler.reset()
        # 重置后可再次触发
        result = scheduler.check_triggers(rules, current_hour=8, current_minute=30)
        assert len(result) == 1


class TestSchedulerCleanupCache:
    """_cleanup_cache 行为测试。"""

    def test_cleanup_removes_expired_entries(self):
        import time

        scheduler = TimeTriggerScheduler()
        # 手动注入过期缓存
        scheduler._fired["old_key"] = time.time() - scheduler._max_cache_age - 1
        scheduler._fired["new_key"] = time.time()
        scheduler._cleanup_cache()
        assert "old_key" not in scheduler._fired
        assert "new_key" in scheduler._fired