"""T22 性能测试 — force 强制投递（spec §4.1 性能 4：≤ 1ms）。"""


import pytest
import time

from src.core.control_message.force_channel import ForceChannel
from src.core.control_message.kind_registry import ControlMessageKindRegistry
from src.core.control_message.mask_manager import ControlMessageMaskManager
from src.core.control_message.priority_dispatcher import PriorityDispatcher
from src.core.control_message.two_level_pending import TwoLevelPendingManager
from src.core.control_message.types import ControlMessageKind
from src.core.control_message.unkillable_guard import UnkillableGuard

# 性能阈值（spec §4.1 性能 4）
FORCE_BUDGET_MS = 1.0
SAMPLES = 200


class _FakeEventBus:
    async def emit(self, event_type: str, data: dict) -> None:
        pass


class TestPerfForce:
    @pytest.mark.asyncio
    async def test_force_deliver(self) -> None:
        """force 强制投递（权限 + 类别 + 清除 + 入队）≤ 1ms。"""
        registry = ControlMessageKindRegistry()
        mask_manager = ControlMessageMaskManager(kind_registry=registry)
        dispatcher = PriorityDispatcher(kind_registry=registry, mask_manager=mask_manager)
        pending = TwoLevelPendingManager(
            kind_registry=registry, priority_dispatcher=dispatcher, mask_manager=mask_manager
        )
        channel = ForceChannel(
            mask_manager=mask_manager,
            unkillable_guard=UnkillableGuard(),
            pending_manager=pending,
            event_bus=_FakeEventBus(),
        )

        # 预热
        for _ in range(20):
            await channel.force_send(ControlMessageKind.EMERGENCY_STOP, caller="watchdog")

        start = time.perf_counter()
        for _ in range(SAMPLES):
            await channel.force_send(ControlMessageKind.EMERGENCY_STOP, caller="watchdog")
        elapsed = time.perf_counter() - start
        per_op_ms = elapsed / SAMPLES * 1e3
        print(f"\nforce 投递均值: {per_op_ms:.3f}ms（预算 {FORCE_BUDGET_MS}ms）")
        assert per_op_ms <= FORCE_BUDGET_MS

    def test_unkillable_check(self) -> None:
        """UNKILLABLE 保护判定 ≤ 5μs（spec §4.1 性能 5）。"""
        guard = UnkillableGuard()
        guard.declare_unkillable("agent:primary")

        start = time.perf_counter()
        for _ in range(2000):
            guard.check_protection("agent:primary", ControlMessageKind.PAUSE_REPLY, force=False)
        elapsed = time.perf_counter() - start
        per_op_us = elapsed / 2000 * 1e6
        print(f"\nUNKILLABLE 判定均值: {per_op_us:.2f}μs（预算 5μs）")
        assert per_op_us <= 5.0
