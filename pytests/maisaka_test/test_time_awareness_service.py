"""time_awareness service 单元测试。

覆盖 TimeAwarenessService 的 get_time_context / check_time_triggers /
build_time_prompt / get_active_coefficient 行为。
"""

from datetime import datetime
from unittest.mock import patch


from src.maisaka.agent.config import AgentConfig, TimeTriggerRule
from src.maisaka.time_awareness.service import TimeAwarenessService


def _make_agent_config(
    morning: float = 0.5,
    afternoon: float = 0.8,
    evening: float = 0.8,
    night: float = 0.3,
    rules: list[TimeTriggerRule] | None = None,
) -> AgentConfig:
    """构造测试用 AgentConfig。"""
    config = AgentConfig()
    config.time_behavior_profile.morning_active_coefficient = morning
    config.time_behavior_profile.afternoon_active_coefficient = afternoon
    config.time_behavior_profile.evening_active_coefficient = evening
    config.time_behavior_profile.night_active_coefficient = night
    if rules is not None:
        config.time_behavior_profile.greeting_rules = rules
    return config


class TestTimeAwarenessServiceInit:
    """TimeAwarenessService 构造测试。"""

    def test_init_creates_builder_and_scheduler(self):
        service = TimeAwarenessService()
        assert service._context_builder is not None
        assert service._scheduler is not None


class TestGetTimeContext:
    """get_time_context 行为测试。"""

    def test_returns_time_context(self):
        service = TimeAwarenessService()
        config = _make_agent_config()
        with patch("src.maisaka.time_awareness.context_builder.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2024, 1, 1, 8, 0, 0)
            ctx = service.get_time_context(config)
        assert ctx is not None
        assert ctx.current_time

    def test_uses_agent_morning_coefficient(self):
        service = TimeAwarenessService()
        config = _make_agent_config(morning=0.95)
        with patch("src.maisaka.time_awareness.context_builder.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2024, 1, 1, 6, 0, 0)
            ctx = service.get_time_context(config)
        assert ctx.active_coefficient == 0.95

    def test_uses_agent_night_coefficient(self):
        service = TimeAwarenessService()
        config = _make_agent_config(night=0.15)
        with patch("src.maisaka.time_awareness.context_builder.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2024, 1, 1, 20, 0, 0)
            ctx = service.get_time_context(config)
        assert ctx.active_coefficient == 0.15


class TestCheckTimeTriggers:
    """check_time_triggers 行为测试。"""

    def test_no_rules_returns_empty(self):
        service = TimeAwarenessService()
        config = _make_agent_config(rules=[])
        result = service.check_time_triggers(config)
        assert result == []

    def test_matching_rule_returns_event(self):
        service = TimeAwarenessService()
        rules = [
            TimeTriggerRule(
                trigger_type="greeting",
                time_range="07:00-09:00",
                message_template="早上好",
            ),
        ]
        config = _make_agent_config(rules=rules)
        with patch("src.maisaka.time_awareness.scheduler.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2024, 1, 1, 8, 0, 0)
            result = service.check_time_triggers(config)
        assert len(result) == 1
        assert result[0].trigger_type == "greeting"


class TestBuildTimePrompt:
    """build_time_prompt 行为测试。"""

    def test_returns_prompt_text(self):
        service = TimeAwarenessService()
        config = _make_agent_config()
        with patch("src.maisaka.time_awareness.context_builder.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2024, 1, 1, 8, 0, 0)
            prompt = service.build_time_prompt(config)
        assert "当前时间" in prompt
        assert "时段" in prompt

    def test_prompt_contains_weekday(self):
        service = TimeAwarenessService()
        config = _make_agent_config()
        with patch("src.maisaka.time_awareness.context_builder.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2024, 1, 1, 8, 0, 0)
            prompt = service.build_time_prompt(config)
        assert "星期一" in prompt


class TestGetActiveCoefficient:
    """get_active_coefficient 行为测试。"""

    def test_returns_coefficient(self):
        service = TimeAwarenessService()
        config = _make_agent_config(afternoon=1.3)
        with patch("src.maisaka.time_awareness.context_builder.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2024, 1, 1, 15, 0, 0)
            coeff = service.get_active_coefficient(config)
        assert coeff == 1.3

    def test_returns_night_coefficient(self):
        service = TimeAwarenessService()
        config = _make_agent_config(night=0.4)
        with patch("src.maisaka.time_awareness.context_builder.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2024, 1, 1, 23, 30, 0)
            coeff = service.get_active_coefficient(config)
        assert coeff == 0.4