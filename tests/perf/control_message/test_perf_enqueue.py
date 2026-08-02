"""T22 性能测试 — 控制消息入队热路径（spec §4.1 性能 2：单次入队 ≤ 30μs）。"""

import time

from src.core.control_message.kind_registry import ControlMessageKindRegistry
from src.core.control_message.pending_queue import ControlMessagePending
from src.core.control_message.types import ControlMessageKind

# 性能阈值（spec §4.1 性能 2）
ENQUEUE_BUDGET_US = 30.0
# 采样次数（去抖动）
SAMPLES = 2000


def _info() -> dict[str, object]:
    return {"source": "perf", "payload": {"n": 1}, "timestamp": 1.0, "trace_id": "perf"}


class TestPerfEnqueue:
    def test_enqueue_hot_path(self) -> None:
        """单次入队 ≤ 30μs（标准消息，位图 + 链表尾插）。"""
        registry = ControlMessageKindRegistry()
        q = ControlMessagePending(kind_registry=registry, max_nodes=100000)

        # 预热（含 dequeue 恢复空位）
        for _ in range(100):
            q.enqueue(ControlMessageKind.PAUSE_REPLY, _info())
            q.enqueue(ControlMessageKind.URGENT_NOTICE, _info())
            q.dequeue(0, 0)

        # 入队单独计时（不含 dequeue，避免混合开销）
        start = time.perf_counter()
        for _ in range(SAMPLES):
            q.enqueue(ControlMessageKind.PAUSE_REPLY, _info())
            q.enqueue(ControlMessageKind.URGENT_NOTICE, _info())
        elapsed = time.perf_counter() - start
        per_op_us = elapsed / (SAMPLES * 2) * 1e6
        print(f"\n入队均值: {per_op_us:.2f}μs（预算 {ENQUEUE_BUDGET_US}μs）")
        assert per_op_us <= ENQUEUE_BUDGET_US
        # 清空队列
        for _ in range(SAMPLES * 2):
            q.dequeue(0, 0)

    def test_dedup_hot_path(self) -> None:
        """标准消息去重入队 ≤ 30μs（位图命中 + payload 更新 + 移至尾部）。"""
        registry = ControlMessageKindRegistry()
        q = ControlMessagePending(kind_registry=registry, max_nodes=100000)
        q.enqueue(ControlMessageKind.PAUSE_REPLY, _info())
        q.enqueue(ControlMessageKind.RESUME_REPLY, _info())

        start = time.perf_counter()
        for _ in range(SAMPLES):
            q.enqueue(ControlMessageKind.PAUSE_REPLY, _info())
        elapsed = time.perf_counter() - start
        per_op_us = elapsed / SAMPLES * 1e6
        print(f"\n去重入队均值: {per_op_us:.2f}μs（预算 {ENQUEUE_BUDGET_US}μs）")
        assert per_op_us <= ENQUEUE_BUDGET_US

    def test_throughput_5000_per_sec(self) -> None:
        """投递频率 ≥ 5000 次/秒（spec §4.1 性能 6：单次 ≤ 200μs 等效）。"""
        registry = ControlMessageKindRegistry()
        q = ControlMessagePending(kind_registry=registry, max_nodes=100000)

        start = time.perf_counter()
        for _ in range(SAMPLES):
            q.enqueue(ControlMessageKind.URGENT_NOTICE, _info())
        elapsed = time.perf_counter() - start
        rate = SAMPLES / elapsed
        print(f"\n入队吞吐: {rate:.0f} 次/秒（要求 ≥ 5000）")
        assert rate >= 5000
