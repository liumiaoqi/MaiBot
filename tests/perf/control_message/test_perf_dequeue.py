"""T22 性能测试 — 优先级出队热路径（spec §4.1 性能 7：两级出队 ≤ 40μs）。"""


import pytest
import time

from src.core.control_message.kind_registry import ControlMessageKindRegistry
from src.core.control_message.mask_manager import ControlMessageMaskManager
from src.core.control_message.pending_queue import ControlMessagePending
from src.core.control_message.priority_dispatcher import PriorityDispatcher
from src.core.control_message.two_level_pending import TwoLevelPendingManager
from src.core.control_message.types import ControlMessageKind, MaskOperation, MaskScope

# 性能阈值（spec §4.1 性能 7）
DEQUEUE_BUDGET_US = 40.0
# 采样次数
SAMPLES = 2000


def _info() -> dict[str, object]:
    return {"source": "perf", "payload": {}, "timestamp": 1.0, "trace_id": "perf"}


class TestPerfDequeue:
    def _make_ready(self) -> tuple[TwoLevelPendingManager, ControlMessagePending]:
        registry = ControlMessageKindRegistry()
        mask_manager = ControlMessageMaskManager(kind_registry=registry)
        dispatcher = PriorityDispatcher(kind_registry=registry, mask_manager=mask_manager)
        manager = TwoLevelPendingManager(
            kind_registry=registry, priority_dispatcher=dispatcher, mask_manager=mask_manager
        )
        private = ControlMessagePending(kind_registry=registry, max_nodes=256)
        # 私有队列常驻 3 类别（会话控制/普通/实时），模拟真实负载
        private.enqueue(ControlMessageKind.SESSION_STOP, _info())
        private.enqueue(ControlMessageKind.PAUSE_REPLY, _info())
        private.enqueue(ControlMessageKind.URGENT_NOTICE, _info())
        return manager, private

    def test_two_level_dequeue(self) -> None:
        """两级 pending 出队（先私后共）≤ 40μs。"""
        manager, private = self._make_ready()

        # 预热
        for _ in range(100):
            manager.dequeue_next_sync("s1")
            private.enqueue(ControlMessageKind.PAUSE_REPLY, _info())

        start = time.perf_counter()
        for _ in range(SAMPLES):
            manager.dequeue_next_sync("s1")
            private.enqueue(ControlMessageKind.PAUSE_REPLY, _info())
        elapsed = time.perf_counter() - start
        per_op_us = elapsed / SAMPLES * 1e6
        print(f"\n两级出队均值: {per_op_us:.2f}μs（预算 {DEQUEUE_BUDGET_US}μs）")
        assert per_op_us <= DEQUEUE_BUDGET_US

    def test_mask_check(self) -> None:
        """屏蔽判定 ≤ 5μs（spec §4.1 性能 3）。"""
        registry = ControlMessageKindRegistry()
        mask_manager = ControlMessageMaskManager(kind_registry=registry)
        mask_manager.set_blocked(MaskOperation.BLOCK, (1 << 16) - 1, MaskScope.SYSTEM)

        start = time.perf_counter()
        for _ in range(SAMPLES):
            mask_manager.get_effective_mask("s1")
        elapsed = time.perf_counter() - start
        per_op_us = elapsed / SAMPLES * 1e6
        print(f"\n屏蔽判定均值: {per_op_us:.2f}μs（预算 5μs）")
        assert per_op_us <= 5.0

    @pytest.mark.asyncio
    async def test_async_dequeue_lock_overhead(self) -> None:
        """async dequeue_next（持共享锁）≤ 40μs 量级。"""
        manager, private = self._make_ready()

        for _ in range(100):
            await manager.dequeue_next("s1")
            private.enqueue(ControlMessageKind.PAUSE_REPLY, _info())

        start = time.perf_counter()
        for _ in range(1000):
            await manager.dequeue_next("s1")
            private.enqueue(ControlMessageKind.PAUSE_REPLY, _info())
        elapsed = time.perf_counter() - start
        per_op_us = elapsed / 1000 * 1e6
        print(f"\nasync 出队均值: {per_op_us:.2f}μs（预算 {DEQUEUE_BUDGET_US}μs）")
        assert per_op_us <= DEQUEUE_BUDGET_US
