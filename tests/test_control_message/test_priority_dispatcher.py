"""T5 PriorityDispatcher 单元测试 — 优先级投递引擎。"""

from src.core.control_message.kind_registry import ControlMessageKindRegistry
from src.core.control_message.mask_manager import ControlMessageMaskManager
from src.core.control_message.pending_queue import ControlMessagePending
from src.core.control_message.priority_dispatcher import PriorityDispatcher
from src.core.control_message.types import (
    ControlMessageKind,
    MaskOperation,
    MaskScope,
)


def _make_dispatcher() -> tuple[PriorityDispatcher, ControlMessageMaskManager]:
    registry = ControlMessageKindRegistry()
    mask_manager = ControlMessageMaskManager(kind_registry=registry)
    dispatcher = PriorityDispatcher(kind_registry=registry, mask_manager=mask_manager)
    return dispatcher, mask_manager


def _make_pending(max_nodes: int = 256) -> ControlMessagePending:
    return ControlMessagePending(
        kind_registry=ControlMessageKindRegistry(), max_nodes=max_nodes
    )


def _info() -> dict[str, object]:
    return {"source": "test", "payload": {}, "timestamp": 1.0, "trace_id": "t1"}


class TestPriorityChain:
    def test_priority_chain(self) -> None:
        """固定优先级链：EMERGENCY_STOP > ENGINE_FATAL_ERROR > PAUSE_REPLY（spec §5.3.1 规则 1）。"""
        dispatcher, _ = _make_dispatcher()
        private = _make_pending()
        shared = _make_pending()
        shared.enqueue(ControlMessageKind.PAUSE_REPLY, _info())
        shared.enqueue(ControlMessageKind.ENGINE_FATAL_ERROR, _info())
        shared.enqueue(ControlMessageKind.EMERGENCY_STOP, _info())
        assert dispatcher.next_control_message(private, shared, "s1").kind == ControlMessageKind.EMERGENCY_STOP
        assert dispatcher.next_control_message(private, shared, "s1").kind == ControlMessageKind.ENGINE_FATAL_ERROR
        assert dispatcher.next_control_message(private, shared, "s1").kind == ControlMessageKind.PAUSE_REPLY

    def test_sync_priority(self) -> None:
        """同步优先：ENGINE_FATAL_ERROR 优先于 SESSION_STOP（spec §5.3.1 规则 2）。"""
        dispatcher, _ = _make_dispatcher()
        private = _make_pending()
        shared = _make_pending()
        shared.enqueue(ControlMessageKind.SESSION_STOP, _info())
        shared.enqueue(ControlMessageKind.ENGINE_FATAL_ERROR, _info())
        node = dispatcher.next_control_message(private, shared, "s1")
        assert node is not None and node.kind == ControlMessageKind.ENGINE_FATAL_ERROR

    def test_low_number_priority(self) -> None:
        """低编号优先：SESSION_STOP(7) 优先于 SESSION_RESUME(8)（spec §5.3.1 规则 3）。"""
        dispatcher, _ = _make_dispatcher()
        private = _make_pending()
        shared = _make_pending()
        shared.enqueue(ControlMessageKind.SESSION_RESUME, _info())
        shared.enqueue(ControlMessageKind.SESSION_STOP, _info())
        node = dispatcher.next_control_message(private, shared, "s1")
        assert node is not None and node.kind == ControlMessageKind.SESSION_STOP

    def test_mask_filter(self) -> None:
        """屏蔽过滤：PAUSE_REPLY 被屏蔽时 RESUME_REPLY 出队（spec §5.3.1 规则 4）。"""
        dispatcher, mask_manager = _make_dispatcher()
        private = _make_pending()
        shared = _make_pending()
        shared.enqueue(ControlMessageKind.PAUSE_REPLY, _info())
        shared.enqueue(ControlMessageKind.RESUME_REPLY, _info())
        mask_manager.set_blocked(
            MaskOperation.BLOCK,
            1 << (ControlMessageKind.PAUSE_REPLY - 1),
            MaskScope.SYSTEM,
        )
        node = dispatcher.next_control_message(private, shared, "s1")
        assert node is not None and node.kind == ControlMessageKind.RESUME_REPLY

    def test_no_control_passes_user(self) -> None:
        """无控制消息放行用户消息：空队列返回 None（spec §5.3.1 规则 5）。"""
        dispatcher, _ = _make_dispatcher()
        assert dispatcher.next_control_message(_make_pending(), _make_pending(), "s1") is None

    def test_all_blocked_passes_user(self) -> None:
        """全部被屏蔽返回 None，放行用户消息（spec §5.3.1 规则 5 验收）。"""
        dispatcher, mask_manager = _make_dispatcher()
        private = _make_pending()
        shared = _make_pending()
        shared.enqueue(ControlMessageKind.PAUSE_REPLY, _info())
        mask_manager.set_blocked(
            MaskOperation.BLOCK, (1 << 16) - 1, MaskScope.SYSTEM
        )
        assert dispatcher.next_control_message(private, shared, "s1") is None


class TestPrivateFirst:
    def test_private_before_shared(self) -> None:
        """先私后共：私有队列有消息优先出队（spec §5.8.1 规则 2）。"""
        dispatcher, _ = _make_dispatcher()
        private = _make_pending()
        shared = _make_pending()
        # 共享队列有更高优先级消息，但私有队列的消息先出
        shared.enqueue(ControlMessageKind.EMERGENCY_STOP, _info())
        private.enqueue(ControlMessageKind.PAUSE_REPLY, _info())
        node = dispatcher.next_control_message(private, shared, "s1")
        assert node is not None and node.kind == ControlMessageKind.PAUSE_REPLY

    def test_private_empty_scans_shared(self) -> None:
        """私有队列空扫描共享队列。"""
        dispatcher, _ = _make_dispatcher()
        private = _make_pending()
        shared = _make_pending()
        shared.enqueue(ControlMessageKind.PAUSE_REPLY, _info())
        node = dispatcher.next_control_message(private, shared, "s1")
        assert node is not None and node.kind == ControlMessageKind.PAUSE_REPLY

    def test_private_all_blocked_falls_to_shared(self) -> None:
        """私有队列全被屏蔽时扫描共享队列。"""
        dispatcher, mask_manager = _make_dispatcher()
        private = _make_pending()
        shared = _make_pending()
        private.enqueue(ControlMessageKind.RESUME_REPLY, _info())
        shared.enqueue(ControlMessageKind.PAUSE_REPLY, _info())
        mask_manager.set_blocked(
            MaskOperation.BLOCK,
            1 << (ControlMessageKind.RESUME_REPLY - 1),
            MaskScope.SESSION,
            "s1",
        )
        node = dispatcher.next_control_message(private, shared, "s1")
        assert node is not None and node.kind == ControlMessageKind.PAUSE_REPLY
