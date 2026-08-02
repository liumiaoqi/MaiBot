"""ZG-7 T3/T5 测试 — TaintAction 枚举 + TaintActionMapper。"""

import pytest

from src.core.tainted_mask.taint_action import TaintAction
from src.core.tainted_mask.taint_action_mapper import TaintActionMapper
from src.core.tainted_mask.taint_flag import TaintFlag


class TestTaintAction:
    def test_action_values(self) -> None:
        """RECORD/WARN/TRIGGER_DEGRADE 值正确（spec §2.3.1 规则 1）。"""
        assert TaintAction.RECORD.value == "record"
        assert TaintAction.WARN.value == "warn"
        assert TaintAction.TRIGGER_DEGRADE.value == "trigger_degrade"

    def test_no_panic_action(self) -> None:
        """不含 PANIC/FATAL（spec §2.3.1 规则 6 禁止项）。"""
        names = {action.name for action in TaintAction}
        assert "PANIC" not in names
        assert "FATAL" not in names


class TestTaintActionMapper:
    def test_default_record(self) -> None:
        """未配置标志默认 RECORD（spec §2.3.1 规则 1）。"""
        mapper = TaintActionMapper({})
        assert mapper.get_action(TaintFlag.TAINT_PORT_BYPASS) is TaintAction.RECORD

    def test_configured_action(self) -> None:
        mapper = TaintActionMapper(
            {TaintFlag.TAINT_PORT_BYPASS: TaintAction.TRIGGER_DEGRADE}
        )
        assert mapper.get_action(TaintFlag.TAINT_PORT_BYPASS) is TaintAction.TRIGGER_DEGRADE
        assert mapper.get_action(TaintFlag.TAINT_WARN) is TaintAction.RECORD

    def test_from_config(self) -> None:
        """配置字典构建映射正确。"""
        mapper = TaintActionMapper.from_config(
            {"TAINT_PORT_BYPASS": "trigger_degrade", "TAINT_WARN": "warn"}
        )
        assert mapper.get_action(TaintFlag.TAINT_PORT_BYPASS) is TaintAction.TRIGGER_DEGRADE
        assert mapper.get_action(TaintFlag.TAINT_WARN) is TaintAction.WARN
        assert mapper.get_action(TaintFlag.TAINT_TEST_MODE) is TaintAction.RECORD

    def test_from_config_empty(self) -> None:
        mapper = TaintActionMapper.from_config({})
        assert mapper.get_action(TaintFlag.TAINT_PORT_BYPASS) is TaintAction.RECORD

    def test_from_config_invalid_flag_name(self) -> None:
        """非法标志名抛 ValueError（design §8.3）。"""
        with pytest.raises(ValueError, match="非法污染标志名"):
            TaintActionMapper.from_config({"TAINT_NOPE": "record"})

    def test_from_config_invalid_action_value(self) -> None:
        """非法动作值抛 ValueError。"""
        with pytest.raises(ValueError, match="非法污染动作值"):
            TaintActionMapper.from_config({"TAINT_WARN": "panic"})
