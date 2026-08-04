"""T7 UnkillableGuard 单元测试 — UNKILLABLE 保护引擎。"""

from src.core.control_message.types import (
    ControlMessageKind,
    ProtectionAction,
)
from src.core.control_message.unkillable_guard import UnkillableGuard


class TestDeclare:
    def test_declare_unkillable(self) -> None:
        """声明 UNKILLABLE：Orchestrator 声明主智能体 A，A 的 is_active=True（spec §5.6.1 规则 1）。"""
        guard = UnkillableGuard()
        guard.declare_unkillable("agent:primary")
        assert guard.is_protected("agent:primary")
        decls = guard.list_unkillable_entities()
        assert len(decls) == 1
        assert decls[0].entity_id == "agent:primary"
        assert decls[0].declared_by == "orchestrator"
        assert decls[0].is_active is True

    def test_config_entities_registered(self) -> None:
        class FakeConfigPort:
            def get_control_message_unkillable_entities(self) -> list[str]:
                return ["agent:primary", "component:orchestrator"]

        guard = UnkillableGuard(app_config_port=FakeConfigPort())
        assert guard.is_protected("agent:primary")
        assert guard.is_protected("component:orchestrator")
        assert len(guard.list_unkillable_entities()) == 2


class TestCheckProtection:
    def test_fatal_rejected(self) -> None:
        """普通致命拒绝：A 设 UNKILLABLE，投递 SESSION_DESTROY → REJECTED（spec §5.6.1 规则 2）。"""
        guard = UnkillableGuard()
        guard.declare_unkillable("agent:primary")
        result = guard.check_protection("agent:primary", ControlMessageKind.SESSION_DESTROY, force=False)
        assert result.action is ProtectionAction.REJECTED
        assert result.reason == "CONTROL_UNKILLABLE_PROTECTED"

    def test_force_clears_unkillable(self) -> None:
        """force 清除：A 设 UNKILLABLE，force 投递 SESSION_DESTROY → CLEARED，A 可淘汰（spec §5.6.1 规则 3）。"""
        guard = UnkillableGuard()
        guard.declare_unkillable("agent:primary")
        result = guard.check_protection("agent:primary", ControlMessageKind.SESSION_DESTROY, force=True)
        assert result.action is ProtectionAction.CLEARED
        assert not guard.is_protected("agent:primary")
        # 声明保留（审计记录）
        assert len(guard.list_unkillable_entities()) == 1

    def test_non_fatal_not_protected(self) -> None:
        """非致命不受保护：A 设 UNKILLABLE，投递 PAUSE_REPLY → PROCEED（spec §5.6.1 规则 4）。"""
        guard = UnkillableGuard()
        guard.declare_unkillable("agent:primary")
        result = guard.check_protection("agent:primary", ControlMessageKind.PAUSE_REPLY, force=False)
        assert result.action is ProtectionAction.PROCEED
        # 保护状态不被非致命消息破坏
        assert guard.is_protected("agent:primary")

    def test_unprotected_entity_proceeds(self) -> None:
        """非 UNKILLABLE 实体正常投递。"""
        guard = UnkillableGuard()
        result = guard.check_protection("agent:other", ControlMessageKind.SESSION_DESTROY, force=False)
        assert result.action is ProtectionAction.PROCEED

    def test_cleared_declaration_no_longer_protects(self) -> None:
        """force 清除后（is_active=False）不再保护，普通致命也可通过。"""
        guard = UnkillableGuard()
        guard.declare_unkillable("agent:primary")
        guard.clear_unkillable("agent:primary")
        result = guard.check_protection("agent:primary", ControlMessageKind.SESSION_DESTROY, force=False)
        assert result.action is ProtectionAction.PROCEED

    def test_config_entity_protected(self) -> None:
        """配置实体受保护：配置清单实体对普通致命拒绝。"""
        class FakeConfigPort:
            def get_control_message_unkillable_entities(self) -> list[str]:
                return ["agent:primary"]

        guard = UnkillableGuard(app_config_port=FakeConfigPort())
        result = guard.check_protection("agent:primary", ControlMessageKind.SESSION_DESTROY, force=False)
        assert result.action is ProtectionAction.REJECTED

    def test_force_fatal_on_config_entity(self) -> None:
        """force 对配置实体也清除保护。"""
        class FakeConfigPort:
            def get_control_message_unkillable_entities(self) -> list[str]:
                return ["agent:primary"]

        guard = UnkillableGuard(app_config_port=FakeConfigPort())
        result = guard.check_protection("agent:primary", ControlMessageKind.SESSION_DESTROY, force=True)
        assert result.action is ProtectionAction.CLEARED
        assert not guard.is_protected("agent:primary")


class TestClearAndList:
    def test_clear_unkillable_keeps_record(self) -> None:
        """clear_unkillable 保留声明（is_active=False，审计记录不销毁）。"""
        guard = UnkillableGuard()
        guard.declare_unkillable("agent:primary")
        guard.clear_unkillable("agent:primary")
        decls = guard.list_unkillable_entities()
        assert len(decls) == 1
        assert decls[0].is_active is False

    def test_list_returns_all_declarations(self) -> None:
        guard = UnkillableGuard()
        guard.declare_unkillable("agent:primary")
        guard.declare_unkillable("component:message_port", entity_type="component")
        assert len(guard.list_unkillable_entities()) == 2


class TestEngineFatalProtection:
    """FATAL_MASK 扩展：引擎致命（4/5/6）触发保护（CX 审核 P1-1，tasks 3.2）。"""

    def test_engine_fatal_rejected(self) -> None:
        """UNKILLABLE 实体 + 4/5/6 → REJECTED（spec §5.6.1 规则 2）。"""
        guard = UnkillableGuard()
        guard.declare_unkillable("agent:primary")
        for kind in (
            ControlMessageKind.ENGINE_FATAL_ERROR,
            ControlMessageKind.MEMORY_SUBSYSTEM_FAILURE,
            ControlMessageKind.SESSION_CORRUPTED,
        ):
            result = guard.check_protection("agent:primary", kind, force=False)
            assert result.action is ProtectionAction.REJECTED, kind
            assert result.reason == "CONTROL_UNKILLABLE_PROTECTED"

    def test_engine_fatal_force_cleared(self) -> None:
        """force + 4/5/6 → CLEARED（spec §5.6.1 规则 3）。"""
        guard = UnkillableGuard()
        for kind in (
            ControlMessageKind.ENGINE_FATAL_ERROR,
            ControlMessageKind.MEMORY_SUBSYSTEM_FAILURE,
            ControlMessageKind.SESSION_CORRUPTED,
        ):
            guard.declare_unkillable("agent:primary")
            result = guard.check_protection("agent:primary", kind, force=True)
            assert result.action is ProtectionAction.CLEARED, kind
            assert not guard.is_protected("agent:primary")

    def test_non_fatal_still_proceed(self) -> None:
        """非致命（12）仍 PROCEED（spec §5.6.1 规则 4 不变性）。"""
        guard = UnkillableGuard()
        guard.declare_unkillable("agent:primary")
        result = guard.check_protection("agent:primary", ControlMessageKind.PAUSE_REPLY, force=False)
        assert result.action is ProtectionAction.PROCEED
