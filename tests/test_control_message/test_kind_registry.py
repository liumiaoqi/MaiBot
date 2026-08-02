"""T3 ControlMessageKindRegistry 单元测试 — 分类与编号引擎。"""

import pytest

from src.core.control_message.kind_registry import ControlMessageKindRegistry
from src.core.control_message.types import (
    ControlMessageCategory,
    ControlMessageKind,
)


class TestKindRegistry:
    def setup_method(self) -> None:
        self.registry = ControlMessageKindRegistry()

    # ── 类别映射（spec §5.1.1 规则 1）──────────────────────────────

    def test_category_system_force(self) -> None:
        for kind in (ControlMessageKind.EMERGENCY_STOP, ControlMessageKind.FORCE_SHUTDOWN, ControlMessageKind.FORCE_OFFLINE):
            assert self.registry.get_category(kind) is ControlMessageCategory.SYSTEM_FORCE

    def test_category_engine_fatal(self) -> None:
        for kind in (
            ControlMessageKind.ENGINE_FATAL_ERROR,
            ControlMessageKind.MEMORY_SUBSYSTEM_FAILURE,
            ControlMessageKind.SESSION_CORRUPTED,
        ):
            assert self.registry.get_category(kind) is ControlMessageCategory.ENGINE_FATAL

    def test_category_session_control(self) -> None:
        for kind in (
            ControlMessageKind.SESSION_STOP,
            ControlMessageKind.SESSION_RESUME,
            ControlMessageKind.SESSION_DESTROY,
        ):
            assert self.registry.get_category(kind) is ControlMessageCategory.SESSION_CONTROL

    def test_category_debug_trace(self) -> None:
        for kind in (ControlMessageKind.DEBUG_TRACE, ControlMessageKind.INSPECT_REQUEST):
            assert self.registry.get_category(kind) is ControlMessageCategory.DEBUG_TRACE

    def test_category_normal(self) -> None:
        for kind in (
            ControlMessageKind.PAUSE_REPLY,
            ControlMessageKind.RESUME_REPLY,
            ControlMessageKind.RELOAD_CONFIG,
        ):
            assert self.registry.get_category(kind) is ControlMessageCategory.NORMAL

    def test_category_realtime(self) -> None:
        for kind in (ControlMessageKind.URGENT_NOTICE, ControlMessageKind.RATE_LIMIT_HIT):
            assert self.registry.get_category(kind) is ControlMessageCategory.REALTIME

    # ── 掩码查询（spec §5.1.1 规则 2-4）────────────────────────────

    def test_is_synchronous(self) -> None:
        for kind in ControlMessageKind:
            expected = kind in (
                ControlMessageKind.ENGINE_FATAL_ERROR,
                ControlMessageKind.MEMORY_SUBSYSTEM_FAILURE,
                ControlMessageKind.SESSION_CORRUPTED,
            )
            assert self.registry.is_synchronous(kind) is expected

    def test_is_unmaskable(self) -> None:
        for kind in ControlMessageKind:
            expected = kind in (
                ControlMessageKind.EMERGENCY_STOP,
                ControlMessageKind.FORCE_SHUTDOWN,
                ControlMessageKind.FORCE_OFFLINE,
            )
            assert self.registry.is_unmaskable(kind) is expected

    def test_is_standard(self) -> None:
        for kind in ControlMessageKind:
            expected = kind not in (
                ControlMessageKind.URGENT_NOTICE,
                ControlMessageKind.RATE_LIMIT_HIT,
            )
            assert self.registry.is_standard(kind) is expected

    def test_is_realtime(self) -> None:
        for kind in ControlMessageKind:
            expected = kind in (
                ControlMessageKind.URGENT_NOTICE,
                ControlMessageKind.RATE_LIMIT_HIT,
            )
            assert self.registry.is_realtime(kind) is expected

    # ── 致命判定（spec §5.9.1 规则 1）──────────────────────────────

    def test_is_fatal_only_session_destroy(self) -> None:
        for kind in ControlMessageKind:
            assert self.registry.is_fatal(kind) is (kind == ControlMessageKind.SESSION_DESTROY)

    # ── 编号越界（spec §5.1.2 异常场景 1）──────────────────────────

    @pytest.mark.parametrize("bad_kind", [0, 17, 99, -1])
    def test_out_of_range_raises(self, bad_kind: int) -> None:
        with pytest.raises(ValueError, match="CONTROL_KIND_UNKNOWN"):
            self.registry.get_category(bad_kind)
        with pytest.raises(ValueError, match="CONTROL_KIND_UNKNOWN"):
            self.registry.is_synchronous(bad_kind)
        with pytest.raises(ValueError, match="CONTROL_KIND_UNKNOWN"):
            self.registry.is_unmaskable(bad_kind)
        with pytest.raises(ValueError, match="CONTROL_KIND_UNKNOWN"):
            self.registry.is_fatal(bad_kind)

    # ── 白名单配置（spec §5.1.2 异常场景 2：配置冲突拒绝保持默认）──

    def test_default_whitelist(self) -> None:
        assert self.registry.unmaskable_whitelist == frozenset(
            {
                ControlMessageKind.EMERGENCY_STOP,
                ControlMessageKind.FORCE_SHUTDOWN,
                ControlMessageKind.FORCE_OFFLINE,
            }
        )

    def test_valid_whitelist_config_accepted(self) -> None:
        class FakeConfigPort:
            def get_control_message_unmaskable_whitelist(self) -> set[int]:
                return {1, 2, 3}

        registry = ControlMessageKindRegistry(app_config_port=FakeConfigPort())
        assert registry.unmaskable_whitelist == frozenset({ControlMessageKind(k) for k in (1, 2, 3)})

    def test_conflicting_whitelist_config_rejected(self) -> None:
        # 配置含不可屏蔽之外类别或缺失 → 拒绝该配置项，保持默认白名单
        class BadConfigPort:
            def get_control_message_unmaskable_whitelist(self) -> set[int]:
                return {1, 2, 3, 12}

        registry = ControlMessageKindRegistry(app_config_port=BadConfigPort())
        assert registry.unmaskable_whitelist == frozenset({ControlMessageKind(k) for k in (1, 2, 3)})
