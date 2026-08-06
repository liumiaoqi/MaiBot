"""ZG-14 T1.9 — ErrorLevel / ErrorAction 枚举语义测试。"""

import json

from src.core.error_escalation.types import ErrorAction, ErrorLevel


class TestErrorLevel:
    """spec §6.1：四级字符串枚举 + 序比较 + JSON 序列化。"""

    def test_values(self) -> None:
        assert [level.value for level in ErrorLevel] == ["warn", "error", "critical", "fatal"]

    def test_order_comparison(self) -> None:
        assert ErrorLevel.WARN < ErrorLevel.ERROR < ErrorLevel.CRITICAL < ErrorLevel.FATAL
        assert ErrorLevel.FATAL >= ErrorLevel.CRITICAL
        assert ErrorLevel.WARN <= ErrorLevel.WARN
        assert ErrorLevel.CRITICAL > ErrorLevel.WARN

    def test_crash_dump_min_level_comparison(self) -> None:
        """CRITICAL 及以上触发快照：ERROR < CRITICAL。"""
        assert ErrorLevel.ERROR < ErrorLevel.CRITICAL
        assert ErrorLevel.CRITICAL >= ErrorLevel.CRITICAL

    def test_json_serialization(self) -> None:
        data = json.dumps({"level": ErrorLevel.CRITICAL.value})
        assert json.loads(data) == {"level": "critical"}
        assert ErrorLevel(json.loads(data)["level"]) is ErrorLevel.CRITICAL

    def test_from_value(self) -> None:
        assert ErrorLevel("warn") is ErrorLevel.WARN
        assert ErrorLevel("fatal") is ErrorLevel.FATAL

    def test_same_level_not_less(self) -> None:
        assert not (ErrorLevel.WARN < ErrorLevel.WARN)


class TestErrorAction:
    """spec §6.2：九种动作 + 无杀进程语义。"""

    def test_values(self) -> None:
        assert [action.value for action in ErrorAction] == [
            "log",
            "taint",
            "count",
            "degrade",
            "report_fault",
            "crash_dump",
            "restart_component",
            "stop_core",
            "notify",
        ]

    def test_no_kill_semantics(self) -> None:
        """禁止 panic/kill/exit 杀进程语义（N2 裁决，spec §6.2 规则 3）。"""
        assert {"panic", "kill", "exit"} & {action.value for action in ErrorAction} == set()
