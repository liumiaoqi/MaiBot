"""ZG-14 T1.9 — ErrorEscalationConfig 校验与回退测试。"""

from src.core.error_escalation.config import DEFAULT_LEVEL_ACTIONS, ErrorEscalationConfig, build_config
from src.core.error_escalation.types import ErrorAction, ErrorLevel


class TestDefaultConfig:
    """spec §6.3 默认值 + 全默认加载（spec §5.8.3 异常场景 1）。"""

    def test_all_defaults(self) -> None:
        config = ErrorEscalationConfig()
        assert config.error_on_warn is False
        assert config.warn_error_threshold == 0
        assert config.critical_on_error is False
        assert config.error_critical_threshold == 0
        assert config.critical_fatal_threshold == 0
        assert config.level_actions is None
        assert config.count_window_sec == 0.0
        assert config.crash_dump_min_level is ErrorLevel.CRITICAL
        assert config.storm_min_threshold == 100

    def test_mapping_none_falls_back_all_defaults(self) -> None:
        config, issues = build_config(None)
        assert config == ErrorEscalationConfig()
        assert any("缺失" in issue for issue in issues)

    def test_mapping_empty_dict_uses_defaults(self) -> None:
        config, issues = build_config({})
        assert config == ErrorEscalationConfig()
        assert issues == []


class TestValidation:
    """spec §5.8.1 规则 4 校验失败回退 + 告警。"""

    def test_negative_threshold_falls_back_disabled(self) -> None:
        config, issues = build_config({"warn_error_threshold": -1})
        assert config.warn_error_threshold == 0
        assert any("负数" in issue for issue in issues)

    def test_all_negative_thresholds(self) -> None:
        config, issues = build_config(
            {"warn_error_threshold": -1, "error_critical_threshold": -5, "critical_fatal_threshold": -3}
        )
        assert config.warn_error_threshold == 0
        assert config.error_critical_threshold == 0
        assert config.critical_fatal_threshold == 0
        assert len(issues) == 3

    def test_invalid_level_actions_falls_back_none(self) -> None:
        config, issues = build_config({"level_actions": {"warn": ["log", "bogus_action"]}})
        assert config.level_actions is None
        assert any("非法动作" in issue for issue in issues)

    def test_invalid_level_actions_key(self) -> None:
        config, issues = build_config({"level_actions": {"bogus_level": ["log"]}})
        assert config.level_actions is None
        assert len(issues) == 1

    def test_invalid_level_actions_type(self) -> None:
        config, issues = build_config({"level_actions": "not-a-dict"})
        assert config.level_actions is None
        assert len(issues) == 1

    def test_invalid_crash_dump_min_level(self) -> None:
        config, issues = build_config({"crash_dump_min_level": "bogus"})
        assert config.crash_dump_min_level is ErrorLevel.CRITICAL
        assert len(issues) == 1

    def test_invalid_window_negative(self) -> None:
        config, issues = build_config({"count_window_sec": -5})
        assert config.count_window_sec == 0.0
        assert len(issues) == 1

    def test_invalid_storm_min_threshold(self) -> None:
        config, issues = build_config({"storm_min_threshold": 0})
        assert config.storm_min_threshold == 100
        assert len(issues) == 1


class TestParsing:
    """字符串/枚举混合来源解析（JSON 配置加载）。"""

    def test_bool_strings(self) -> None:
        config, _ = build_config({"error_on_warn": "true", "critical_on_error": 1})
        assert config.error_on_warn is True
        assert config.critical_on_error is True

    def test_level_actions_string_keys_and_values(self) -> None:
        config, issues = build_config({"level_actions": {"warn": ["log"]}})
        assert issues == []
        assert config.level_actions == {ErrorLevel.WARN: [ErrorAction.LOG]}

    def test_level_actions_enum_keys_and_values(self) -> None:
        config, _ = build_config({"level_actions": {ErrorLevel.ERROR: [ErrorAction.DEGRADE]}})
        assert config.level_actions == {ErrorLevel.ERROR: [ErrorAction.DEGRADE]}

    def test_crash_dump_min_level_string(self) -> None:
        config, issues = build_config({"crash_dump_min_level": "fatal"})
        assert issues == []
        assert config.crash_dump_min_level is ErrorLevel.FATAL


class TestActionsFor:
    """level_actions 覆盖默认，未覆盖的等级用默认（spec §5.3.1 规则 1）。"""

    def test_default_actions(self) -> None:
        config = ErrorEscalationConfig()
        assert config.actions_for(ErrorLevel.WARN) == (
            ErrorAction.LOG,
            ErrorAction.TAINT,
            ErrorAction.COUNT,
        )
        assert config.actions_for(ErrorLevel.ERROR) == (
            ErrorAction.LOG,
            ErrorAction.TAINT,
            ErrorAction.COUNT,
            ErrorAction.DEGRADE,
            ErrorAction.REPORT_FAULT,
        )
        assert config.actions_for(ErrorLevel.CRITICAL) == (
            ErrorAction.LOG,
            ErrorAction.CRASH_DUMP,
            ErrorAction.RESTART_COMPONENT,
            ErrorAction.NOTIFY,
        )
        assert config.actions_for(ErrorLevel.FATAL) == (
            ErrorAction.LOG,
            ErrorAction.CRASH_DUMP,
            ErrorAction.STOP_CORE,
            ErrorAction.NOTIFY,
        )

    def test_override_only_matching_level(self) -> None:
        config, _ = build_config({"level_actions": {ErrorLevel.WARN: [ErrorAction.LOG]}})
        assert config.actions_for(ErrorLevel.WARN) == (ErrorAction.LOG,)
        # 未覆盖的 ERROR 仍用默认
        assert ErrorAction.DEGRADE in config.actions_for(ErrorLevel.ERROR)

    def test_default_level_actions_structure(self) -> None:
        """design §2.3.2 默认动作集表。"""
        assert set(DEFAULT_LEVEL_ACTIONS) == set(ErrorLevel)
        assert ErrorAction.STOP_CORE in DEFAULT_LEVEL_ACTIONS[ErrorLevel.FATAL]
        assert ErrorAction.CRASH_DUMP in DEFAULT_LEVEL_ACTIONS[ErrorLevel.CRITICAL]
        # 无杀进程语义动作（N2 裁决，spec §6.2 规则 3）
        for actions in DEFAULT_LEVEL_ACTIONS.values():
            assert not {a.value for a in actions} & {"panic", "kill", "exit"}
