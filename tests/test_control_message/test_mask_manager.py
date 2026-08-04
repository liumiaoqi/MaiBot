"""T6 ControlMessageMaskManager 单元测试 — 屏蔽机制引擎。"""

from src.core.control_message.mask_manager import ControlMessageMaskManager
from src.core.control_message.types import (
    UNMASKABLE_MASK,
    ControlMessageKind,
    MaskOperation,
    MaskScope,
)


def _bit(kind: ControlMessageKind) -> int:
    return 1 << (kind - 1)


class TestSetBlocked:
    def test_block_union(self) -> None:
        """BLOCK 并集：{12} BLOCK {13} → {12,13}（spec §5.4.1 规则 2）。"""
        m = ControlMessageMaskManager()
        m.set_blocked(MaskOperation.BLOCK, _bit(ControlMessageKind.PAUSE_REPLY), MaskScope.SYSTEM)
        result = m.set_blocked(
            MaskOperation.BLOCK, _bit(ControlMessageKind.RESUME_REPLY), MaskScope.SYSTEM
        )
        assert result == _bit(ControlMessageKind.PAUSE_REPLY) | _bit(ControlMessageKind.RESUME_REPLY)

    def test_unblock_diff(self) -> None:
        """UNBLOCK 差集：{12,13} UNBLOCK {12} → {13}（spec §5.4.1 规则 2）。"""
        m = ControlMessageMaskManager()
        m.set_blocked(
            MaskOperation.BLOCK,
            _bit(ControlMessageKind.PAUSE_REPLY) | _bit(ControlMessageKind.RESUME_REPLY),
            MaskScope.SYSTEM,
        )
        result = m.set_blocked(
            MaskOperation.UNBLOCK, _bit(ControlMessageKind.PAUSE_REPLY), MaskScope.SYSTEM
        )
        assert result == _bit(ControlMessageKind.RESUME_REPLY)

    def test_setmask_direct(self) -> None:
        """SETMASK 直接设置（spec §5.4.1 规则 2）。"""
        m = ControlMessageMaskManager()
        m.set_blocked(MaskOperation.BLOCK, _bit(ControlMessageKind.PAUSE_REPLY), MaskScope.SYSTEM)
        result = m.set_blocked(
            MaskOperation.SETMASK, _bit(ControlMessageKind.RELOAD_CONFIG), MaskScope.SYSTEM
        )
        assert result == _bit(ControlMessageKind.RELOAD_CONFIG)

    def test_unmaskable_force_removed(self) -> None:
        """不可屏蔽强制剔除：SETMASK {1,12} → {12}（spec §5.4.1 规则 3）。"""
        m = ControlMessageMaskManager()
        result = m.set_blocked(
            MaskOperation.SETMASK,
            _bit(ControlMessageKind.EMERGENCY_STOP) | _bit(ControlMessageKind.PAUSE_REPLY),
            MaskScope.SYSTEM,
        )
        assert result == _bit(ControlMessageKind.PAUSE_REPLY)

    def test_block_unmaskable_rejected(self) -> None:
        """尝试 BLOCK {1} 拒绝，EMERGENCY_STOP 不入屏蔽集（spec §5.4.1 规则 6）。"""
        m = ControlMessageMaskManager()
        result = m.set_blocked(
            MaskOperation.BLOCK, _bit(ControlMessageKind.EMERGENCY_STOP), MaskScope.SYSTEM
        )
        assert result == 0


class TestSetIgnored:
    def test_ignored_set(self) -> None:
        m = ControlMessageMaskManager()
        result = m.set_ignored(_bit(ControlMessageKind.PAUSE_REPLY), MaskScope.SYSTEM)
        assert result == _bit(ControlMessageKind.PAUSE_REPLY)
        assert m.get_effective_mask("").ignored_bits == _bit(ControlMessageKind.PAUSE_REPLY)

    def test_ignored_unmaskable_rejected(self) -> None:
        """忽略判定拒绝：忽略集含 EMERGENCY_STOP 被剔除（spec §5.5.1 第二道防线）。"""
        m = ControlMessageMaskManager()
        result = m.set_ignored(
            _bit(ControlMessageKind.EMERGENCY_STOP) | _bit(ControlMessageKind.PAUSE_REPLY),
            MaskScope.SYSTEM,
        )
        assert result == _bit(ControlMessageKind.PAUSE_REPLY)


class TestEffectiveMask:
    def test_two_level_mask_union(self) -> None:
        """两级屏蔽：系统级 {12} ∪ 会话级 {13} = 有效 {12,13}（spec §5.4.1 规则 5）。"""
        m = ControlMessageMaskManager()
        m.set_blocked(MaskOperation.BLOCK, _bit(ControlMessageKind.PAUSE_REPLY), MaskScope.SYSTEM)
        m.set_blocked(
            MaskOperation.BLOCK, _bit(ControlMessageKind.RESUME_REPLY), MaskScope.SESSION, "s1"
        )
        eff_s1 = m.get_effective_mask("s1")
        eff_s2 = m.get_effective_mask("s2")
        assert eff_s1.blocked_bits == _bit(ControlMessageKind.PAUSE_REPLY) | _bit(
            ControlMessageKind.RESUME_REPLY
        )
        assert eff_s2.blocked_bits == _bit(ControlMessageKind.PAUSE_REPLY)

    def test_session_mask_isolated(self) -> None:
        m = ControlMessageMaskManager()
        m.set_blocked(MaskOperation.BLOCK, _bit(ControlMessageKind.PAUSE_REPLY), MaskScope.SESSION, "s1")
        assert m.get_effective_mask("s2").blocked_bits == 0

    def test_ignored_union(self) -> None:
        m = ControlMessageMaskManager()
        m.set_ignored(_bit(ControlMessageKind.PAUSE_REPLY), MaskScope.SYSTEM)
        m.set_ignored(_bit(ControlMessageKind.RESUME_REPLY), MaskScope.SESSION, "s1")
        assert m.get_effective_mask("s1").ignored_bits == _bit(
            ControlMessageKind.PAUSE_REPLY
        ) | _bit(ControlMessageKind.RESUME_REPLY)


class TestForceClear:
    def test_clear_blocked_bit(self) -> None:
        """force 清除屏蔽：force 投递到已屏蔽目标，屏蔽被清除（spec §5.7.1 规则 1）。"""
        m = ControlMessageMaskManager()
        m.set_blocked(MaskOperation.BLOCK, _bit(ControlMessageKind.PAUSE_REPLY), MaskScope.SESSION, "s1")
        m.clear_blocked_bit(ControlMessageKind.PAUSE_REPLY, "s1")
        assert m.get_effective_mask("s1").blocked_bits == 0

    def test_clear_ignored_bit(self) -> None:
        m = ControlMessageMaskManager()
        m.set_ignored(_bit(ControlMessageKind.PAUSE_REPLY), MaskScope.SYSTEM)
        m.clear_ignored_bit(ControlMessageKind.PAUSE_REPLY)
        assert m.get_effective_mask("").ignored_bits == 0

    def test_force_clear_system_and_session(self) -> None:
        """force 清除同时作用于系统级与会话级。"""
        m = ControlMessageMaskManager()
        m.set_blocked(MaskOperation.BLOCK, _bit(ControlMessageKind.PAUSE_REPLY), MaskScope.SYSTEM)
        m.set_blocked(
            MaskOperation.BLOCK, _bit(ControlMessageKind.PAUSE_REPLY), MaskScope.SESSION, "s1"
        )
        m.clear_blocked_bit(ControlMessageKind.PAUSE_REPLY, "s1")
        assert m.get_effective_mask("s1").blocked_bits == 0


class TestMisc:
    def test_config_loaded_masks(self) -> None:
        class FakeConfigPort:
            def get_control_message_system_blocked_kinds(self) -> set[int]:
                return {12}

            def get_control_message_system_ignored_kinds(self) -> set[int]:
                return {13}

        m = ControlMessageMaskManager(app_config_port=FakeConfigPort())
        eff = m.get_effective_mask("")
        assert eff.blocked_bits == _bit(ControlMessageKind.PAUSE_REPLY)
        assert eff.ignored_bits == _bit(ControlMessageKind.RESUME_REPLY)

    def test_drop_session_mask(self) -> None:
        m = ControlMessageMaskManager()
        m.set_blocked(MaskOperation.BLOCK, _bit(ControlMessageKind.PAUSE_REPLY), MaskScope.SESSION, "s1")
        m.drop_session_mask("s1")
        assert m.get_effective_mask("s1").blocked_bits == 0

    def test_unmaskable_mask_constant(self) -> None:
        """UNMASKABLE_MASK 覆盖编号 1-3 对应位。"""
        assert UNMASKABLE_MASK == _bit(ControlMessageKind.EMERGENCY_STOP) | _bit(
            ControlMessageKind.FORCE_SHUTDOWN
        ) | _bit(ControlMessageKind.FORCE_OFFLINE)



class TestDynamicUnmaskable:
    """动态不可屏蔽掩码（CX 审核 P1-4，tasks 7.2，spec §5.5.1 规则 2）。"""

    def test_default_fallback_static_mask(self) -> None:
        """kind_registry=None 时回退静态 UNMASKABLE_MASK（行为不变）。"""
        m = ControlMessageMaskManager(kind_registry=None)
        result = m.set_blocked(
            MaskOperation.SETMASK,
            _bit(ControlMessageKind.EMERGENCY_STOP) | _bit(ControlMessageKind.PAUSE_REPLY),
            MaskScope.SYSTEM,
        )
        assert result == _bit(ControlMessageKind.PAUSE_REPLY)  # 1-3 被剔除

    def test_extended_whitelist_forced_out(self) -> None:
        """白名单 {1,2,3,4} 时 kind=4 也被强制剔除（动态掩码）。"""
        from src.core.control_message.kind_registry import ControlMessageKindRegistry

        class _FakeConfig:
            def get_control_message_unmaskable_whitelist(self) -> set[int]:
                return {1, 2, 3, 4}

        registry = ControlMessageKindRegistry(app_config_port=_FakeConfig())
        assert registry.unmaskable_mask == 0xF  # bit0-3 = kind 1-4
        m = ControlMessageMaskManager(kind_registry=registry)
        result = m.set_blocked(
            MaskOperation.SETMASK,
            _bit(ControlMessageKind.ENGINE_FATAL_ERROR) | _bit(ControlMessageKind.PAUSE_REPLY),
            MaskScope.SYSTEM,
        )
        assert result == _bit(ControlMessageKind.PAUSE_REPLY)  # kind=4 被剔除

    def test_unmaskable_mask_lifetime_invariant(self) -> None:
        """unmaskable_mask 在 KindRegistry 生命周期内不变（运行时不可修改）。"""
        from src.core.control_message.kind_registry import ControlMessageKindRegistry

        registry = ControlMessageKindRegistry()
        before = registry.unmaskable_mask
        _ = registry.unmaskable_whitelist  # 只读访问不改变状态
        assert registry.unmaskable_mask == before == UNMASKABLE_MASK
