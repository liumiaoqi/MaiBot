"""T4 ControlMessagePending 单元测试 — 双结构待处理队列引擎。"""

import pytest

from src.core.control_message.kind_registry import ControlMessageKindRegistry
from src.core.control_message.pending_queue import ControlMessagePending
from src.core.control_message.types import (
    ControlMessageKind,
)


def _make_queue(max_nodes: int = 256) -> ControlMessagePending:
    return ControlMessagePending(
        kind_registry=ControlMessageKindRegistry(), max_nodes=max_nodes
    )


def _info(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "source": "test",
        "payload": {},
        "timestamp": 1.0,
        "trace_id": "t1",
    }
    base.update(overrides)
    return base


class TestEnqueue:
    def test_enqueue_standard_adds_node(self) -> None:
        q = _make_queue()
        result = q.enqueue(ControlMessageKind.PAUSE_REPLY, _info())
        assert result.accepted is True
        assert result.deduplicated is False
        assert q.node_count == 1
        assert q.has_pending(ControlMessageKind.PAUSE_REPLY)

    def test_standard_dedup_keeps_count_updates_payload(self) -> None:
        """标准消息去重：节点数不变，payload 更新为最新（spec §5.2.1 规则 2）。"""
        q = _make_queue()
        q.enqueue(ControlMessageKind.PAUSE_REPLY, _info(payload={"v": 1}))
        result = q.enqueue(ControlMessageKind.PAUSE_REPLY, _info(payload={"v": 2}))
        assert result.accepted is True
        assert result.deduplicated is True
        assert q.node_count == 1
        assert q.node_list[0].info["payload"] == {"v": 2}

    def test_realtime_queues_all_instances(self) -> None:
        """实时消息排队：两次投递节点数 +2，按 FIFO（spec §5.2.1 规则 3）。"""
        q = _make_queue()
        q.enqueue(ControlMessageKind.URGENT_NOTICE, _info(payload={"n": 1}))
        q.enqueue(ControlMessageKind.URGENT_NOTICE, _info(payload={"n": 2}))
        assert q.node_count == 2
        assert q.node_list[0].info["payload"] == {"n": 1}
        assert q.node_list[1].info["payload"] == {"n": 2}

    def test_dedup_moves_to_tail(self) -> None:
        """链表保序：投 A(13)、B(12)、A(13) → 链表 [B, A']，出队 B→A（spec §5.2.1 规则 4）。"""
        q = _make_queue()
        q.enqueue(ControlMessageKind.RESUME_REPLY, _info(payload={"a": 1}))  # 13
        q.enqueue(ControlMessageKind.PAUSE_REPLY, _info(payload={"b": 1}))  # 12
        q.enqueue(ControlMessageKind.RESUME_REPLY, _info(payload={"a": 2}))  # 13 去重移至尾
        assert [n.kind for n in q.node_list] == [
            ControlMessageKind.PAUSE_REPLY,
            ControlMessageKind.RESUME_REPLY,
        ]
        # 低编号优先：PAUSE_REPLY(12) 先出，RESUME_REPLY(13) 后出
        first = q.dequeue(0, 0)
        second = q.dequeue(0, 0)
        assert first is not None and first.kind == ControlMessageKind.PAUSE_REPLY
        assert second is not None and second.kind == ControlMessageKind.RESUME_REPLY
        assert second.info["payload"] == {"a": 2}

    def test_overflow_low_priority_rejected(self) -> None:
        """队列溢出：满时低优先级新消息无法驱逐任何节点被拒绝（spec §5.2.1 规则 6/7）。"""
        q = _make_queue(max_nodes=2)
        q.enqueue(ControlMessageKind.PAUSE_REPLY, _info())
        q.enqueue(ControlMessageKind.RESUME_REPLY, _info())
        result = q.enqueue(ControlMessageKind.RATE_LIMIT_HIT, _info())
        assert result.accepted is False
        assert result.reason == "CONTROL_PENDING_OVERFLOW"

    def test_overflow_high_priority_evicts(self) -> None:
        """队列溢出：满时高优先级新消息驱逐低优先级节点后入队（spec §5.2.1 规则 7）。"""
        q = _make_queue(max_nodes=2)
        q.enqueue(ControlMessageKind.PAUSE_REPLY, _info(payload={"v": 1}))
        q.enqueue(ControlMessageKind.RESUME_REPLY, _info(payload={"v": 2}))
        result = q.enqueue(ControlMessageKind.EMERGENCY_STOP, _info())
        assert result.accepted is True
        assert q.node_count == 2
        kinds = [n.kind for n in q.node_list]
        assert ControlMessageKind.EMERGENCY_STOP in kinds


class TestDequeue:
    def test_dequeue_empty(self) -> None:
        q = _make_queue()
        assert q.dequeue(0, 0) is None

    def test_mask_filter_keeps_blocked(self) -> None:
        """屏蔽过滤：被屏蔽消息不出队，留在 pending（spec §5.3.1 规则 4）。"""
        q = _make_queue()
        q.enqueue(ControlMessageKind.PAUSE_REPLY, _info())
        q.enqueue(ControlMessageKind.RESUME_REPLY, _info())
        blocked = 1 << (ControlMessageKind.RESUME_REPLY - 1)
        node = q.dequeue(blocked, 0)
        assert node is not None and node.kind == ControlMessageKind.PAUSE_REPLY
        # RESUME_REPLY 仍留 pending
        assert q.has_pending(ControlMessageKind.RESUME_REPLY)
        # 全部被屏蔽 → None
        q.enqueue(ControlMessageKind.PAUSE_REPLY, _info())
        assert q.dequeue(0b1111_1111_1111_1111, 0) is None

    def test_sync_priority(self) -> None:
        """同步优先：ENGINE_FATAL_ERROR 优先于 SESSION_STOP（spec §5.3.1 规则 2）。"""
        q = _make_queue()
        q.enqueue(ControlMessageKind.SESSION_STOP, _info())
        q.enqueue(ControlMessageKind.ENGINE_FATAL_ERROR, _info())
        node = q.dequeue(0, 0)
        assert node is not None and node.kind == ControlMessageKind.ENGINE_FATAL_ERROR

    def test_low_number_first(self) -> None:
        """低编号优先：SESSION_STOP(7) 优先于 SESSION_RESUME(8)（spec §5.3.1 规则 3）。"""
        q = _make_queue()
        q.enqueue(ControlMessageKind.SESSION_RESUME, _info())
        q.enqueue(ControlMessageKind.SESSION_STOP, _info())
        node = q.dequeue(0, 0)
        assert node is not None and node.kind == ControlMessageKind.SESSION_STOP

    def test_force_priority_chain(self) -> None:
        """固定优先级链：EMERGENCY_STOP(1) > ENGINE_FATAL_ERROR(4) > PAUSE_REPLY(12)（spec §5.3.1 规则 1）。"""
        q = _make_queue()
        q.enqueue(ControlMessageKind.PAUSE_REPLY, _info())
        q.enqueue(ControlMessageKind.ENGINE_FATAL_ERROR, _info())
        q.enqueue(ControlMessageKind.EMERGENCY_STOP, _info())
        assert q.dequeue(0, 0).kind == ControlMessageKind.EMERGENCY_STOP
        assert q.dequeue(0, 0).kind == ControlMessageKind.ENGINE_FATAL_ERROR
        assert q.dequeue(0, 0).kind == ControlMessageKind.PAUSE_REPLY

    def test_force_over_sync_priority(self) -> None:
        """系统级强制 > 同步优先：EMERGENCY_STOP 与 ENGINE_FATAL_ERROR 同时 pending 时先出前者（spec §5.3.1 规则 2 验收）。"""
        q = _make_queue()
        q.enqueue(ControlMessageKind.ENGINE_FATAL_ERROR, _info())
        q.enqueue(ControlMessageKind.EMERGENCY_STOP, _info())
        assert q.dequeue(0, 0).kind == ControlMessageKind.EMERGENCY_STOP

    def test_ignored_filter(self) -> None:
        """忽略过滤：被忽略类别不出队。"""
        q = _make_queue()
        q.enqueue(ControlMessageKind.PAUSE_REPLY, _info())
        ignored = 1 << (ControlMessageKind.PAUSE_REPLY - 1)
        assert q.dequeue(0, ignored) is None

    def test_bitmap_consistency_after_dequeue(self) -> None:
        """位图与链表一致性：出队后位图正确清除。"""
        q = _make_queue()
        q.enqueue(ControlMessageKind.PAUSE_REPLY, _info())
        q.enqueue(ControlMessageKind.URGENT_NOTICE, _info())
        q.dequeue(0, 0)
        assert not q.has_pending(ControlMessageKind.PAUSE_REPLY)
        assert q.has_pending(ControlMessageKind.URGENT_NOTICE)
        # 实时同类别剩 1 个时位图保留
        q.dequeue(0, 0)
        assert not q.has_pending(ControlMessageKind.URGENT_NOTICE)
        assert q.node_count == 0

    def test_fifo_within_kind(self) -> None:
        """同类别（实时）FIFO：先入先出。"""
        q = _make_queue()
        q.enqueue(ControlMessageKind.URGENT_NOTICE, _info(payload={"n": 1}))
        q.enqueue(ControlMessageKind.URGENT_NOTICE, _info(payload={"n": 2}))
        first = q.dequeue(0, 0)
        second = q.dequeue(0, 0)
        assert first.info["payload"] == {"n": 1}
        assert second.info["payload"] == {"n": 2}


class TestHasPending:
    def test_has_pending_o1(self) -> None:
        q = _make_queue()
        assert not q.has_pending(ControlMessageKind.PAUSE_REPLY)
        q.enqueue(ControlMessageKind.PAUSE_REPLY, _info())
        assert q.has_pending(ControlMessageKind.PAUSE_REPLY)
        q.dequeue(0, 0)
        assert not q.has_pending(ControlMessageKind.PAUSE_REPLY)

    @pytest.mark.parametrize(
        "kind",
        [
            ControlMessageKind.EMERGENCY_STOP,
            ControlMessageKind.SESSION_DESTROY,
            ControlMessageKind.RATE_LIMIT_HIT,
        ],
    )
    def test_has_pending_any_kind(self, kind: ControlMessageKind) -> None:
        q = _make_queue()
        q.enqueue(kind, _info())
        assert q.has_pending(kind)

    def test_is_full(self) -> None:
        q = _make_queue(max_nodes=1)
        assert not q.is_full()
        q.enqueue(ControlMessageKind.PAUSE_REPLY, _info())
        assert q.is_full()


class TestPriorityEvictionExt:
    """优先级感知溢出驱逐补全（CX 审核 P1-6，tasks 8.3）。"""

    def test_eviction_target_is_lowest_priority(self) -> None:
        """驱逐对象断言：4 驱逐 13（编号最大），不是任意节点（CX 强化断言）。"""
        q = _make_queue(max_nodes=2)
        q.enqueue(ControlMessageKind.PAUSE_REPLY, _info(payload={"v": 1}))    # 12
        q.enqueue(ControlMessageKind.RESUME_REPLY, _info(payload={"v": 2}))   # 13
        result = q.enqueue(ControlMessageKind.ENGINE_FATAL_ERROR, _info())    # 4
        assert result.accepted is True
        kinds = sorted(int(n.kind) for n in q.node_list)
        assert kinds == [4, 12]  # 13 被驱逐

    def test_same_priority_no_eviction(self) -> None:
        """同优先级不驱逐：15 驱逐不了 15（实时消息不去重，spec §5.2.1 规则 7）。

        标准消息同类别会被去重分支拦截（P2-3 修复后去重优先于溢出），
        故用实时消息验证"编号不大于则不驱逐"。
        """
        q = _make_queue(max_nodes=1)
        q.enqueue(ControlMessageKind.URGENT_NOTICE, _info())
        result = q.enqueue(ControlMessageKind.URGENT_NOTICE, _info())
        assert result.accepted is False
        assert "CONTROL_PENDING_OVERFLOW" in result.reason

    def test_unmaskable_not_evictable(self) -> None:
        """1-3 不可驱逐：仅 EMERGENCY_STOP(1) 时 FORCE_SHUTDOWN(2) 无法入队。"""
        q = _make_queue(max_nodes=1)
        q.enqueue(ControlMessageKind.EMERGENCY_STOP, _info())
        result = q.enqueue(ControlMessageKind.FORCE_SHUTDOWN, _info())
        assert result.accepted is False

    def test_fatal_evicts_realtime(self) -> None:
        """标准高优先级驱逐实时低优先级：4 驱逐 15。"""
        q = _make_queue(max_nodes=1)
        q.enqueue(ControlMessageKind.URGENT_NOTICE, _info())
        result = q.enqueue(ControlMessageKind.ENGINE_FATAL_ERROR, _info())
        assert result.accepted is True
        assert [int(n.kind) for n in q.node_list] == [4]

    def test_eviction_bitmap_consistency(self) -> None:
        """驱逐后位图一致性：被驱逐类别无剩余节点时清位。"""
        q = _make_queue(max_nodes=2)
        q.enqueue(ControlMessageKind.PAUSE_REPLY, _info())   # 12
        q.enqueue(ControlMessageKind.RESUME_REPLY, _info())  # 13
        q.enqueue(ControlMessageKind.ENGINE_FATAL_ERROR, _info())  # 4 驱逐 13
        assert q.kind_bitmap & (1 << (ControlMessageKind.RESUME_REPLY - 1)) == 0  # 13 位清
        assert q.kind_bitmap & (1 << (ControlMessageKind.ENGINE_FATAL_ERROR - 1)) != 0  # 4 位置
        assert q.kind_bitmap & (1 << (ControlMessageKind.PAUSE_REPLY - 1)) != 0  # 12 位保留

    def test_eviction_logged(self) -> None:
        """驱逐日志含 priority_eviction（spec §5.2.1 规则 7 验收）。"""
        from unittest.mock import patch

        q = _make_queue(max_nodes=1)
        q.enqueue(ControlMessageKind.PAUSE_REPLY, _info())
        with patch("src.core.control_message.pending_queue.logger") as mock_logger:
            q.enqueue(ControlMessageKind.ENGINE_FATAL_ERROR, _info())
        assert mock_logger.info.call_count == 1
        assert "priority_eviction" in mock_logger.info.call_args[0][0]
