"""T11 ControlMessageAdapter 集成测试 — 组装 8 引擎，实现 ControlMessagePort。"""

import pytest

from src.core.adapters.control_message_adapter import ControlMessageAdapter
from src.core.protocols import ControlMessagePort
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

    def emit_sync(self, event_type: str, data: dict) -> None:
        self.events.append((event_type, data))


class _FakeServiceManager:
    def __init__(self) -> None:
        self.faults: list[tuple[str, str, str]] = []

    async def report_external_fault(self, component_id: str, reason: str, detail: str) -> None:
        self.faults.append((component_id, reason, detail))


class _FakeLifecycle:
    def __init__(self) -> None:
        self.cancelled: list[str] = []

    async def list_session_async_tasks(self, session_id: str) -> list:
        return []


def _make_adapter() -> tuple[ControlMessageAdapter, _FakeEventBus, _FakeLifecycle]:
    bus = _FakeEventBus()
    sm = _FakeServiceManager()
    lifecycle = _FakeLifecycle()
    adapter = ControlMessageAdapter(
        event_bus_port=bus,
        service_manager_port=sm,
        session_lifecycle_port=lifecycle,
    )
    return adapter, bus, lifecycle


class TestPortContract:
    def test_isinstance_control_message_port(self) -> None:
        """isinstance(adapter, ControlMessagePort) == True（spec §7.1 微内核隔离）。"""
        adapter, _, _ = _make_adapter()
        assert isinstance(adapter, ControlMessagePort)

    def test_all_port_methods_present(self) -> None:
        """ControlMessagePort 全部 14 个方法存在。"""
        adapter, _, _ = _make_adapter()
        for method in (
            "send",
            "force_send",
            "dequeue_next",
            "set_blocked",
            "set_ignored",
            "get_effective_mask",
            "declare_unkillable",
            "clear_unkillable",
            "list_unkillable_entities",
            "on_session_created",
            "on_session_destroyed",
            "get_pending_view",
            "get_delivery_history",
            "get_diffuse_history",
        ):
            assert hasattr(adapter, method), f"missing: {method}"


class TestSendFlow:
    @pytest.mark.asyncio
    async def test_send_queued(self) -> None:
        """send 完整流程：入队 QUEUED。"""
        adapter, bus, _ = _make_adapter()
        await adapter.on_session_created("s1")
        result = await adapter.send(
            ControlMessageKind.PAUSE_REPLY, {"reason": "quiet"}, target_session_id="s1", source="webui"
        )
        assert result.delivered is False
        assert result.result is DeliveryResult.QUEUED
        assert adapter.get_pending_view("s1").total_count == 1

    @pytest.mark.asyncio
    async def test_send_ignored_dropped(self) -> None:
        """send 忽略判定：被忽略类别直接丢弃不入队。"""
        adapter, _, _ = _make_adapter()
        await adapter.set_ignored({ControlMessageKind.PAUSE_REPLY}, MaskScope.SYSTEM)
        result = await adapter.send(ControlMessageKind.PAUSE_REPLY, {}, target_session_id="s1")
        assert result.result is DeliveryResult.REJECTED_IGNORED
        assert adapter.get_pending_view("s1").total_count == 0

    @pytest.mark.asyncio
    async def test_send_unkillable_protected(self) -> None:
        """send UNKILLABLE 保护：致命消息到受保护实体被拒绝。"""
        adapter, bus, _ = _make_adapter()
        await adapter.declare_unkillable("agent:primary")
        result = await adapter.send(
            ControlMessageKind.SESSION_DESTROY, {}, target_entity="agent:primary"
        )
        assert result.result is DeliveryResult.REJECTED_UNKILLABLE
        assert any(t == "control.unkillable_protected" for t, _ in bus.events)

    @pytest.mark.asyncio
    async def test_send_invalid_kind(self) -> None:
        adapter, _, _ = _make_adapter()
        with pytest.raises(ValueError, match="CONTROL_KIND_UNKNOWN"):
            await adapter.send(99, {})

    @pytest.mark.asyncio
    async def test_send_fatal_triggers_diffuse(self) -> None:
        """致命扩散：SESSION_DESTROY 触发扩散。"""
        adapter, _, _ = _make_adapter()
        await adapter.on_session_created("s1")
        result = await adapter.send(
            ControlMessageKind.SESSION_DESTROY, {}, target_session_id="s1"
        )
        assert result.result is DeliveryResult.QUEUED
        # 扩散异步执行，等待历史记录
        for _ in range(50):
            if adapter.get_diffuse_history():
                break
            import asyncio

            await asyncio.sleep(0.01)
        assert len(adapter.get_diffuse_history()) == 1


class TestDequeueFlow:
    @pytest.mark.asyncio
    async def test_dequeue_priority_order(self) -> None:
        """优先级投递：EMERGENCY_STOP > ENGINE_FATAL_ERROR > PAUSE_REPLY。"""
        adapter, _, _ = _make_adapter()
        await adapter.send(ControlMessageKind.PAUSE_REPLY, {})
        await adapter.send(ControlMessageKind.ENGINE_FATAL_ERROR, {})
        await adapter.send(ControlMessageKind.EMERGENCY_STOP, {})
        assert adapter.dequeue_next("s1").kind == ControlMessageKind.EMERGENCY_STOP
        assert adapter.dequeue_next("s1").kind == ControlMessageKind.ENGINE_FATAL_ERROR
        assert adapter.dequeue_next("s1").kind == ControlMessageKind.PAUSE_REPLY

    @pytest.mark.asyncio
    async def test_dequeue_none_when_empty(self) -> None:
        """无控制消息放行用户消息：dequeue_next 返回 None。"""
        adapter, _, _ = _make_adapter()
        assert adapter.dequeue_next("s1") is None

    @pytest.mark.asyncio
    async def test_dequeue_payload_conversion(self) -> None:
        """PendingNode → ControlMessage 转换（design §5.1）。"""
        adapter, _, _ = _make_adapter()
        await adapter.send(
            ControlMessageKind.RELOAD_CONFIG,
            {"path": "/etc/bot.toml"},
            source="webui",
            trace_id="trace-1",
        )
        msg = adapter.dequeue_next("s1")
        assert msg is not None
        assert msg.kind == ControlMessageKind.RELOAD_CONFIG
        assert msg.payload == {"path": "/etc/bot.toml"}
        assert msg.source == "webui"
        assert msg.trace_id == "trace-1"
        assert msg.force is False


class TestMaskLifecycle:
    @pytest.mark.asyncio
    async def test_mask_block_unblock_cycle(self) -> None:
        """屏蔽生命周期：屏蔽 → 留 pending → 解除屏蔽 → 按原顺序投递。"""
        adapter, _, _ = _make_adapter()
        await adapter.on_session_created("s1")
        await adapter.send(ControlMessageKind.PAUSE_REPLY, {}, target_session_id="s1")
        await adapter.set_blocked(
            MaskOperation.BLOCK, {ControlMessageKind.PAUSE_REPLY}, MaskScope.SESSION, "s1"
        )
        # 被屏蔽不出队
        assert adapter.dequeue_next("s1") is None
        assert adapter.get_pending_view("s1").total_count == 1
        # 解除屏蔽后投递
        await adapter.set_blocked(
            MaskOperation.UNBLOCK, {ControlMessageKind.PAUSE_REPLY}, MaskScope.SESSION, "s1"
        )
        msg = adapter.dequeue_next("s1")
        assert msg is not None and msg.kind == ControlMessageKind.PAUSE_REPLY

    @pytest.mark.asyncio
    async def test_effective_mask_union(self) -> None:
        adapter, _, _ = _make_adapter()
        await adapter.set_blocked(MaskOperation.BLOCK, {ControlMessageKind.PAUSE_REPLY}, MaskScope.SYSTEM)
        await adapter.set_blocked(
            MaskOperation.BLOCK, {ControlMessageKind.RESUME_REPLY}, MaskScope.SESSION, "s1"
        )
        eff = adapter.get_effective_mask("s1")
        assert eff.blocked_bits & (1 << (ControlMessageKind.PAUSE_REPLY - 1))
        assert eff.blocked_bits & (1 << (ControlMessageKind.RESUME_REPLY - 1))

    def test_get_effective_mask_sync(self) -> None:
        adapter, _, _ = _make_adapter()
        eff = adapter.get_effective_mask("s1")
        assert eff.blocked_bits == 0


class TestForceFlow:
    @pytest.mark.asyncio
    async def test_force_full_flow(self) -> None:
        """force 完整流程：权限 → 清除保护 → 直接入队 → 审计。"""
        adapter, bus, _ = _make_adapter()
        result = await adapter.force_send(
            ControlMessageKind.EMERGENCY_STOP,
            target_session_id="s1",
            reason="test",
            caller="watchdog",
        )
        assert result.result is DeliveryResult.FORCE_DELIVERED
        assert adapter.get_pending_view("").total_count == 1
        assert any(t == "control.force_delivered" for t, _ in bus.events)
        assert len(adapter.get_delivery_history()) >= 1

    @pytest.mark.asyncio
    async def test_force_permission_denied(self) -> None:
        adapter, _, _ = _make_adapter()
        result = await adapter.force_send(
            ControlMessageKind.EMERGENCY_STOP, caller="plugin"
        )
        assert result.delivered is False
        assert "CONTROL_FORCE_PERMISSION_DENIED" in result.detail


class TestSessionLifecycle:
    @pytest.mark.asyncio
    async def test_session_lifecycle_cleanup(self) -> None:
        """会话生命周期：创建 → 投递 → 销毁 → 私有队列清理 + 扩散。"""
        adapter, _, _ = _make_adapter()
        await adapter.on_session_created("s1")
        await adapter.send(ControlMessageKind.PAUSE_REPLY, {}, target_session_id="s1")
        assert adapter.get_pending_view("s1").total_count == 1
        await adapter.on_session_destroyed("s1")
        assert adapter.get_pending_view("s1").total_count == 0

    @pytest.mark.asyncio
    async def test_destroyed_session_falls_back_to_shared(self) -> None:
        adapter, _, _ = _make_adapter()
        await adapter.on_session_created("s1")
        await adapter.on_session_destroyed("s1")
        await adapter.send(ControlMessageKind.PAUSE_REPLY, {}, target_session_id="s1")
        assert adapter.get_pending_view("").total_count == 1


class TestIntrospection:
    @pytest.mark.asyncio
    async def test_pending_view(self) -> None:
        adapter, _, _ = _make_adapter()
        await adapter.send(ControlMessageKind.PAUSE_REPLY, {})
        view = adapter.get_pending_view("")
        assert view.total_count == 1
        assert view.category_bitmap != 0
        assert len(view.nodes) == 1

    @pytest.mark.asyncio
    async def test_delivery_history_limited(self) -> None:
        adapter, _, _ = _make_adapter()
        for i in range(3):
            await adapter.send(ControlMessageKind.PAUSE_REPLY, {"n": i})
        assert len(adapter.get_delivery_history()) == 3
        records = adapter.get_delivery_history()
        assert all(r.kind == ControlMessageKind.PAUSE_REPLY for r in records)
        assert all(r.decision_id for r in records)

    @pytest.mark.asyncio
    async def test_diffuse_history(self) -> None:
        adapter, _, _ = _make_adapter()
        await adapter.send(ControlMessageKind.PAUSE_REPLY, {})
        assert adapter.get_diffuse_history() == []


class TestUnkillableThroughPort:
    @pytest.mark.asyncio
    async def test_unkillable_declare_list_clear(self) -> None:
        adapter, _, _ = _make_adapter()
        await adapter.declare_unkillable("agent:primary")
        decls = adapter.list_unkillable_entities()
        assert len(decls) == 1
        assert decls[0].entity_id == "agent:primary"
        await adapter.clear_unkillable("agent:primary")
        assert not adapter.list_unkillable_entities()[0].is_active
