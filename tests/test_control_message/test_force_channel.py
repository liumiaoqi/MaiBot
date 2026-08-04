"""T8 ForceChannel 单元测试 — force 强制投递引擎。"""

import pytest

from src.core.control_message.kind_registry import ControlMessageKindRegistry
from src.core.control_message.mask_manager import ControlMessageMaskManager
from src.core.control_message.priority_dispatcher import PriorityDispatcher
from src.core.control_message.force_channel import ForceChannel
from src.core.control_message.two_level_pending import TwoLevelPendingManager
from src.core.control_message.types import (
    ControlMessageKind,
    DeliveryResult,
    MaskOperation,
    MaskScope,
)


class _FakeEventBus:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    async def emit(self, event_type: str, data: dict) -> None:
        self.events.append((event_type, data))


def _make_channel() -> tuple[ForceChannel, _FakeEventBus, TwoLevelPendingManager, ControlMessageMaskManager]:
    registry = ControlMessageKindRegistry()
    mask_manager = ControlMessageMaskManager(kind_registry=registry)
    dispatcher = PriorityDispatcher(kind_registry=registry, mask_manager=mask_manager)
    pending = TwoLevelPendingManager(
        kind_registry=registry, priority_dispatcher=dispatcher, mask_manager=mask_manager
    )
    from src.core.control_message.unkillable_guard import UnkillableGuard

    guard = UnkillableGuard()
    bus = _FakeEventBus()
    channel = ForceChannel(
        mask_manager=mask_manager,
        unkillable_guard=guard,
        pending_manager=pending,
        event_bus=bus,
    )
    return channel, bus, pending, mask_manager


class TestPermission:
    @pytest.mark.asyncio
    async def test_non_whitelist_caller_rejected(self) -> None:
        """非白名单调用方拒绝（插件尝试 force → REJECTED，spec §5.7.1 规则 2）。"""
        channel, bus, _, _ = _make_channel()
        result = await channel.force_send(
            ControlMessageKind.EMERGENCY_STOP, caller="plugin:evil"
        )
        assert result.delivered is False
        assert "CONTROL_FORCE_PERMISSION_DENIED" in result.detail
        assert ("control.force_denied", "plugin:evil") == (
            bus.events[0][0],
            bus.events[0][1]["caller"],
        )

    @pytest.mark.asyncio
    async def test_whitelist_caller_allowed(self) -> None:
        """白名单调用方允许（watchdog 调用 → FORCE_DELIVERED，spec §5.7.1 规则 2）。"""
        channel, bus, pending, _ = _make_channel()
        result = await channel.force_send(
            ControlMessageKind.EMERGENCY_STOP, target_session_id="s1", caller="watchdog"
        )
        assert result.delivered is True
        assert result.result is DeliveryResult.FORCE_DELIVERED
        assert pending.get_pending_view("")[3] == 1

    @pytest.mark.asyncio
    async def test_non_force_kind_rejected(self) -> None:
        """非系统级强制类别拒绝（force PAUSE_REPLY → REJECTED，spec §5.7.1 规则 5）。"""
        channel, _, pending, _ = _make_channel()
        result = await channel.force_send(
            ControlMessageKind.PAUSE_REPLY, caller="watchdog"
        )
        assert result.delivered is False
        assert "CONTROL_FORCE_KIND_INVALID" in result.detail
        assert pending.get_pending_view("")[3] == 0


class TestForceDelivery:
    @pytest.mark.asyncio
    async def test_force_clears_blocked(self) -> None:
        """force 穿透屏蔽：目标会话屏蔽其他类别时 force 消息仍可投递（spec §5.7.1 规则 1）。

        EMERGENCY_STOP(1) 不可被屏蔽（不可屏蔽剔除），force 清除的是自身类别位；
        屏蔽的其他类别（PAUSE_REPLY）不被误清除。
        """
        channel, _, pending, mask_manager = _make_channel()
        mask_manager.set_blocked(
            MaskOperation.BLOCK,
            1 << (ControlMessageKind.PAUSE_REPLY - 1),
            MaskScope.SESSION,
            "s1",
        )
        result = await channel.force_send(
            ControlMessageKind.EMERGENCY_STOP, target_session_id="s1", caller="watchdog"
        )
        assert result.delivered is True
        # force 消息可出队（穿透屏蔽）
        node = await pending.dequeue_next("s1")
        assert node is not None and node.kind == ControlMessageKind.EMERGENCY_STOP
        # 其他类别屏蔽不被误清除
        assert mask_manager.get_effective_mask("s1").blocked_bits == (
            1 << (ControlMessageKind.PAUSE_REPLY - 1)
        )

    @pytest.mark.asyncio
    async def test_force_clears_unkillable(self) -> None:
        """force 清除 UNKILLABLE：force 投递到 UNKILLABLE 目标，标志被清除（spec §5.6.1 规则 3）。"""
        from src.core.control_message.unkillable_guard import UnkillableGuard

        registry = ControlMessageKindRegistry()
        mask_manager = ControlMessageMaskManager(kind_registry=registry)
        dispatcher = PriorityDispatcher(kind_registry=registry, mask_manager=mask_manager)
        pending = TwoLevelPendingManager(
            kind_registry=registry, priority_dispatcher=dispatcher, mask_manager=mask_manager
        )
        guard = UnkillableGuard()
        guard.declare_unkillable("agent:primary")
        bus = _FakeEventBus()
        channel = ForceChannel(
            mask_manager=mask_manager,
            unkillable_guard=guard,
            pending_manager=pending,
            event_bus=bus,
        )
        result = await channel.force_send(
            ControlMessageKind.EMERGENCY_STOP,
            target_entity="agent:primary",
            caller="watchdog",
        )
        assert result.delivered is True
        assert not guard.is_protected("agent:primary")
        assert any(t == "control.unkillable_cleared" for t, _ in bus.events)

    @pytest.mark.asyncio
    async def test_force_delivered_event_published(self) -> None:
        """发布 control.force_delivered 事件（spec §5.7.1 规则 4）。"""
        channel, bus, _, _ = _make_channel()
        await channel.force_send(
            ControlMessageKind.EMERGENCY_STOP, target_session_id="s1", caller="watchdog"
        )
        assert any(t == "control.force_delivered" for t, _ in bus.events)
        event = next(d for t, d in bus.events if t == "control.force_delivered")
        assert event["caller"] == "watchdog"
        assert event["kind"] == 1
        assert event["target"] == "s1"

    @pytest.mark.asyncio
    async def test_force_audit_info_in_pending(self) -> None:
        """force 入队消息携带 force=true 与原因（审计链路）。"""
        channel, _, pending, _ = _make_channel()
        await channel.force_send(
            ControlMessageKind.EMERGENCY_STOP,
            target_session_id="s1",
            reason="watchdog timeout",
            caller="watchdog",
        )
        node = await pending.dequeue_next("s1")
        assert node is not None
        assert node.info["force"] is True
        assert node.info["reason"] == "watchdog timeout"
        assert node.info["source"] == "watchdog"


class TestKindValidationExt:
    """force 类别扩展 1-6（CX 审核 P1-3，tasks 5.2，spec §5.7.1 规则 5 / §6.9）。"""

    @pytest.mark.asyncio
    async def test_engine_fatal_allowed(self) -> None:
        """force 允许引擎致命 4-6 → FORCE_DELIVERED。"""
        channel, bus, _, _ = _make_channel()
        for kind in (
            ControlMessageKind.ENGINE_FATAL_ERROR,
            ControlMessageKind.MEMORY_SUBSYSTEM_FAILURE,
            ControlMessageKind.SESSION_CORRUPTED,
        ):
            result = await channel.force_send(kind, caller="watchdog")
            assert result.delivered is True, kind
            assert result.result is DeliveryResult.FORCE_DELIVERED

    @pytest.mark.asyncio
    async def test_session_control_rejected(self) -> None:
        """force 拒绝会话控制 7-9 → CONTROL_FORCE_KIND_INVALID。"""
        channel, bus, _, _ = _make_channel()
        for kind in (
            ControlMessageKind.SESSION_STOP,
            ControlMessageKind.SESSION_RESUME,
            ControlMessageKind.SESSION_DESTROY,
        ):
            result = await channel.force_send(kind, caller="watchdog")
            assert result.delivered is False, kind
            assert "CONTROL_FORCE_KIND_INVALID" in result.detail

    @pytest.mark.asyncio
    async def test_normal_realtime_rejected(self) -> None:
        """force 拒绝普通 12-14 与实时 15-16。"""
        channel, bus, _, _ = _make_channel()
        for kind in (
            ControlMessageKind.PAUSE_REPLY,
            ControlMessageKind.RELOAD_CONFIG,
            ControlMessageKind.URGENT_NOTICE,
            ControlMessageKind.RATE_LIMIT_HIT,
        ):
            result = await channel.force_send(kind, caller="watchdog")
            assert result.delivered is False, kind
            assert "CONTROL_FORCE_KIND_INVALID" in result.detail
