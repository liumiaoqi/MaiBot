"""ZG-14 T1.9 — EnumLevelMapper 14 枚举映射 + 4 冲突消解测试。"""

from src.core.error_escalation.mapper import EnumLevelMapper
from src.core.error_escalation.types import ErrorLevel
from src.core.resource_limit.types import OOMAction, PressureLevel
from src.core.service_manager.types import RecoveryAction, ServiceState
from src.core.startup.types import ComponentStatus
from src.core.tainted_mask.taint_action import TaintAction
from src.core.watchdog.types import BlockSeverity

mapper = EnumLevelMapper()


class TestStaticMapping:
    """无冲突枚举映射（spec §5.6.1 规则 1 的 14 项中无冲突部分）。"""

    def test_taint_action(self) -> None:
        assert mapper.map(TaintAction.WARN) is ErrorLevel.WARN
        assert mapper.map(TaintAction.TRIGGER_DEGRADE) is ErrorLevel.ERROR

    def test_oom_action(self) -> None:
        assert mapper.map(OOMAction.DEGRADE) is ErrorLevel.ERROR
        assert mapper.map(OOMAction.KILL) is ErrorLevel.CRITICAL

    def test_service_state_simple(self) -> None:
        assert mapper.map(ServiceState.FAULT) is ErrorLevel.ERROR
        assert mapper.map(ServiceState.DEGRADED) is ErrorLevel.WARN

    def test_block_severity(self) -> None:
        assert mapper.map(BlockSeverity.MILD_LAG) is ErrorLevel.WARN
        assert mapper.map(BlockSeverity.SEVERE_BLOCK) is ErrorLevel.ERROR

    def test_pressure_level(self) -> None:
        assert mapper.map(PressureLevel.MEDIUM) is ErrorLevel.WARN
        assert mapper.map(PressureLevel.CRITICAL) is ErrorLevel.CRITICAL

    def test_unknown_enum_falls_back_warn(self) -> None:
        """未知枚举按 WARN 兜底（spec §5.6.3 异常场景 1）。"""
        assert mapper.map("bogus") is ErrorLevel.WARN


class TestConflictResolution:
    """4 个冲突消解（spec §5.6.1 规则 2-5）。"""

    def test_service_state_fault_manual_storm_protection(self) -> None:
        """风暴保护场景 → CRITICAL（验收场景 10）。"""
        assert mapper.map(ServiceState.FAULT_MANUAL, storm_protection=True) is ErrorLevel.CRITICAL

    def test_service_state_fault_manual_conservative_fatal(self) -> None:
        """标志缺失按保守原则 FATAL（spec §5.6.3 异常场景 2）。"""
        assert mapper.map(ServiceState.FAULT_MANUAL) is ErrorLevel.FATAL
        assert mapper.map(ServiceState.FAULT_MANUAL, storm_protection=False) is ErrorLevel.FATAL

    def test_component_status_failed_critical_bit(self) -> None:
        assert mapper.map(ComponentStatus.FAILED, critical=True) is ErrorLevel.CRITICAL
        assert mapper.map(ComponentStatus.FAILED, critical=False) is ErrorLevel.ERROR

    def test_recovery_manual_restart_storm_protection(self) -> None:
        assert mapper.map(RecoveryAction.MANUAL_RESTART, storm_protection=True) is ErrorLevel.CRITICAL
        assert mapper.map(RecoveryAction.MANUAL_RESTART) is ErrorLevel.FATAL

    def test_diffuse_scope_single_global(self) -> None:
        """单会话扩散 → CRITICAL；全扩散 → FATAL（spec §5.6.1 规则 5）。"""
        assert mapper.map("single", diffuse_scope="single") is ErrorLevel.CRITICAL
        assert mapper.map("global", diffuse_scope="global") is ErrorLevel.FATAL

    def test_diffuse_scope_missing_conservative_fatal(self) -> None:
        assert mapper.map("global") is ErrorLevel.FATAL  # 标志缺失 → FATAL


class TestMappingTable:
    """映射表可查询 + 全覆盖（spec §5.6.1 规则 7）。"""

    def test_table_has_all_14_entries(self) -> None:
        table = mapper.get_mapping_table()
        assert len(table) == 14

    def test_table_marks_fatal_diffuser_mapping_object(self) -> None:
        """P2-1：映射对象标注为扩散范围状态（single/global）非类本身。"""
        entry = mapper.get_mapping_table()["FatalDiffuser(diffuse_scope)"]
        assert "single" in entry["resolve"]
        assert "global" in entry["resolve"]
