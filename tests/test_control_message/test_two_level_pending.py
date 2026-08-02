"""T9 TwoLevelPendingManager 单元测试 — 两级 pending 引擎。"""

import pytest

from src.core.control_message.kind_registry import ControlMessageKindRegistry
from src.core.control_message.mask_manager import ControlMessageMaskManager
from src.core.control_message.priority_dispatcher import PriorityDispatcher
from src.core.control_message.two_level_pending import TwoLevelPendingManager
from src.core.control_message.types import (
    ControlMessageKind,
)


def _make_manager() -> TwoLevelPendingManager:
    registry = ControlMessageKindRegistry()
    mask_manager = ControlMessageMaskManager(kind_registry=registry)
    dispatcher = PriorityDispatcher(kind_registry=registry, mask_manager=mask_manager)
    return TwoLevelPendingManager(
        kind_registry=registry,
        priority_dispatcher=dispatcher,
        mask_manager=mask_manager,
    )


def _info() -> dict[str, object]:
    return {"source": "test", "payload": {}, "timestamp": 1.0, "trace_id": "t1"}


class TestEnqueue:
    @pytest.mark.asyncio
    async def test_send_to_session_private(self) -> None:
        """定向消息入私有队列（spec §5.8.1 规则 1）。"""
        m = _make_manager()
        m.on_session_created("s1")
        result = await m.send_to_session("s1", ControlMessageKind.PAUSE_REPLY, _info())
        assert result.accepted is True
        view = m.get_pending_view("s1")
        assert view[3] == 1

    @pytest.mark.asyncio
    async def test_send_to_system_shared(self) -> None:
        """全局消息入共享队列（spec §5.8.1 规则 2）。"""
        m = _make_manager()
        result = await m.send_to_system(ControlMessageKind.FORCE_SHUTDOWN, _info())
        assert result.accepted is True
        assert m.get_pending_view("")[3] == 1

    @pytest.mark.asyncio
    async def test_private_missing_falls_back_to_shared(self) -> None:
        """私有队列不存在降级共享队列（spec §5.8.2 异常场景 1）。"""
        m = _make_manager()
        result = await m.send_to_session("s1", ControlMessageKind.PAUSE_REPLY, _info())
        assert result.accepted is True
        assert m.get_pending_view("")[3] == 1

    @pytest.mark.asyncio
    async def test_private_overflow(self) -> None:
        """私有队列溢出（256 节点）拒绝（spec §5.8.1 规则 5）。"""
        m = _make_manager()
        m.on_session_created("s1")
        ok = True
        for _ in range(256):
            ok = (await m.send_to_session("s1", ControlMessageKind.URGENT_NOTICE, _info())).accepted
        assert ok is True
        result = await m.send_to_session("s1", ControlMessageKind.URGENT_NOTICE, _info())
        assert result.accepted is False

    @pytest.mark.asyncio
    async def test_shared_overflow(self) -> None:
        """共享队列溢出（1024 节点）拒绝。"""
        m = _make_manager()
        for _ in range(1024):
            await m.send_to_system(ControlMessageKind.URGENT_NOTICE, _info())
        result = await m.send_to_system(ControlMessageKind.URGENT_NOTICE, _info())
        assert result.accepted is False


class TestDequeue:
    @pytest.mark.asyncio
    async def test_private_first(self) -> None:
        """先私后共：私有队列有消息优先出队（spec §5.8.1 规则 2）。"""
        m = _make_manager()
        m.on_session_created("s1")
        await m.send_to_session("s1", ControlMessageKind.PAUSE_REPLY, _info())
        await m.send_to_system(ControlMessageKind.EMERGENCY_STOP, _info())
        node = await m.dequeue_next("s1")
        assert node is not None and node.kind == ControlMessageKind.PAUSE_REPLY

    @pytest.mark.asyncio
    async def test_shared_fallback(self) -> None:
        """私有空扫共享。"""
        m = _make_manager()
        m.on_session_created("s1")
        await m.send_to_system(ControlMessageKind.PAUSE_REPLY, _info())
        node = await m.dequeue_next("s1")
        assert node is not None and node.kind == ControlMessageKind.PAUSE_REPLY

    @pytest.mark.asyncio
    async def test_no_private_queue_scans_shared(self) -> None:
        """无私队列的会话直接扫共享。"""
        m = _make_manager()
        await m.send_to_system(ControlMessageKind.PAUSE_REPLY, _info())
        node = await m.dequeue_next("s1")
        assert node is not None and node.kind == ControlMessageKind.PAUSE_REPLY

    @pytest.mark.asyncio
    async def test_priority_chain_across_levels(self) -> None:
        """跨级优先级：共享 EMERGENCY_STOP 不被私有 PAUSE_REPLY 阻断（私有优先但同优先级链）。"""
        m = _make_manager()
        m.on_session_created("s1")
        await m.send_to_session("s1", ControlMessageKind.PAUSE_REPLY, _info())
        await m.send_to_system(ControlMessageKind.EMERGENCY_STOP, _info())
        # 先私后共：私有 PAUSE_REPLY 先出
        first = await m.dequeue_next("s1")
        assert first is not None and first.kind == ControlMessageKind.PAUSE_REPLY
        second = await m.dequeue_next("s1")
        assert second is not None and second.kind == ControlMessageKind.EMERGENCY_STOP


class TestForceEnqueue:
    @pytest.mark.asyncio
    async def test_force_enqueue_skips_dedup(self) -> None:
        """force 直接入队绕过去重：标准消息 force 两次保留两个节点。"""
        m = _make_manager()
        m.on_session_created("s1")
        await m.force_enqueue(ControlMessageKind.PAUSE_REPLY, _info(), "s1")
        await m.force_enqueue(ControlMessageKind.PAUSE_REPLY, _info(), "s1")
        assert m.get_pending_view("s1")[3] == 2

    @pytest.mark.asyncio
    async def test_force_enqueue_bypasses_limit(self) -> None:
        """force 入队不受队列上限约束（spec §4.2 可靠性 2 必须成功入队）。"""
        m = _make_manager()
        m.on_session_created("s1")
        for _ in range(300):  # 超过私有上限 256
            await m.force_enqueue(ControlMessageKind.URGENT_NOTICE, _info(), "s1")
        assert m.get_pending_view("s1")[3] == 300

    @pytest.mark.asyncio
    async def test_force_enqueue_shared_without_session(self) -> None:
        m = _make_manager()
        await m.force_enqueue(ControlMessageKind.EMERGENCY_STOP, _info())
        assert m.get_pending_view("")[3] == 1


class TestSessionLifecycle:
    @pytest.mark.asyncio
    async def test_session_destroyed_cleanup(self) -> None:
        """会话销毁清理私有队列（spec §5.8.1 规则 3，防内存泄漏）。"""
        m = _make_manager()
        m.on_session_created("s1")
        await m.send_to_session("s1", ControlMessageKind.PAUSE_REPLY, _info())
        m.on_session_destroyed("s1")
        assert m.get_pending_view("s1")[3] == 0
        # 后续投递降级共享
        await m.send_to_session("s1", ControlMessageKind.PAUSE_REPLY, _info())
        assert m.get_pending_view("")[3] == 1

    def test_on_session_created_idempotent(self) -> None:
        m = _make_manager()
        m.on_session_created("s1")
        m.on_session_created("s1")  # 重复创建不报错
        assert m.get_pending_view("s1")[3] == 0
