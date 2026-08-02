"""资源限制性能测试 — 对应 tasks §10.1。

对标 spec §4.1 性能要求：
- charge 热路径 ≤ 50μs（含父链 10 层）
- charge 吞吐 ≥ 10000 次/秒
- 压力等级计算 ≤ 1ms
- 事件传播 ≤ 5ms（10 层）
- 内省查询 ≤ 100ms（1000 节点）
"""


import time

import pytest

from src.core.resource_limit.pressure_detector import PressureDetector
from src.core.resource_limit.resource_counter import ResourceCounter
from src.core.resource_limit.resource_event_propagator import (
    ResourceEventPropagator,
)
from src.core.resource_limit.resource_limit_config import (
    FourTierLimit,
    ResourceLimitConfig,
    ResourceLimitConfigManager,
)
from src.core.resource_limit.types import PressureLevel, ResourceDimension


class TestPerfCharge:
    """charge 热路径性能。"""

    def test_perf_charge_hot_path(self):
        """单次 charge（含父链 10 层）≤ 50μs。"""
        config_mgr = ResourceLimitConfigManager()
        config_mgr.load_config("n0", ResourceLimitConfig(
            "n0", {ResourceDimension.TOKEN: FourTierLimit(0, 0, 0, 1000000)}
        ))
        counter = ResourceCounter(max_limit_provider=config_mgr.get_max)
        counter.register_plugin("n0")
        for i in range(1, 10):
            counter.register_plugin(f"n{i}", parent_id=f"n{i - 1}")

        # 预热
        for _ in range(100):
            counter.charge("n9", ResourceDimension.TOKEN, 1)
            counter.uncharge("n9", ResourceDimension.TOKEN, 1)

        # 测量
        iterations = 1000
        start = time.perf_counter_ns()
        for _ in range(iterations):
            counter.charge("n9", ResourceDimension.TOKEN, 1)
            counter.uncharge("n9", ResourceDimension.TOKEN, 1)
        elapsed_ns = time.perf_counter_ns() - start
        per_call_us = elapsed_ns / iterations / 2 / 1000

        assert per_call_us <= 50, f"charge 热路径 {per_call_us:.1f}μs > 50μs"

    def test_perf_charge_throughput(self):
        """charge 吞吐 ≥ 10000 次/秒。"""
        config_mgr = ResourceLimitConfigManager()
        config_mgr.load_config("a", ResourceLimitConfig(
            "a", {ResourceDimension.TOKEN: FourTierLimit(0, 0, 0, 100000000)}
        ))
        counter = ResourceCounter(max_limit_provider=config_mgr.get_max)
        counter.register_plugin("a")

        iterations = 10000
        start = time.perf_counter()
        for _ in range(iterations):
            counter.charge("a", ResourceDimension.TOKEN, 1)
            counter.uncharge("a", ResourceDimension.TOKEN, 1)
        elapsed = time.perf_counter() - start
        throughput = iterations / elapsed

        assert throughput >= 10000, f"吞吐 {throughput:.0f} < 10000 次/秒"


class TestPerfPressure:
    """压力等级计算性能。"""

    def test_perf_pressure_calc(self):
        """单次压力等级计算 ≤ 1ms。"""
        pd = PressureDetector(win_size=100)
        pd.window.set_state(0, 0, PressureLevel.LOW)

        # 预热
        for _ in range(100):
            pd.record_sample(100, 50)

        iterations = 1000
        start = time.perf_counter_ns()
        for _ in range(iterations):
            pd.record_sample(100, 50)
        elapsed_ns = time.perf_counter_ns() - start
        per_call_ms = elapsed_ns / iterations / 1_000_000

        assert per_call_ms <= 1, f"压力计算 {per_call_ms:.3f}ms > 1ms"


class TestPerfEventPropagate:
    """事件传播性能。"""

    @pytest.mark.asyncio
    async def test_perf_event_propagate(self):
        """事件向上传播至根（10 层）≤ 5ms。"""
        counter = ResourceCounter()
        counter.register_plugin("n0")
        for i in range(1, 10):
            counter.register_plugin(f"n{i}", parent_id=f"n{i - 1}")

        propagator = ResourceEventPropagator(event_bus=None, dedup_window_ms=0)

        iterations = 1000
        start = time.perf_counter_ns()
        for _ in range(iterations):
            await propagator.propagate(
                "n9", "resource.usage", {"v": 1}, node_provider=counter
            )
        elapsed_ns = time.perf_counter_ns() - start
        per_call_ms = elapsed_ns / iterations / 1_000_000

        assert per_call_ms <= 5, f"事件传播 {per_call_ms:.3f}ms > 5ms"


class TestPerfIntrospect:
    """内省查询性能。"""

    def test_perf_introspect(self):
        """get_resource_tree_view（1000 节点）≤ 100ms。

        直接用 ResourceCounter.all_nodes() + to_snapshot() 模拟适配器内省路径。
        """
        config_mgr = ResourceLimitConfigManager()
        config_mgr.load_config("n0", ResourceLimitConfig(
            "n0", {ResourceDimension.TOKEN: FourTierLimit(0, 0, 0, 1000000)}
        ))
        counter = ResourceCounter(max_limit_provider=config_mgr.get_max)
        counter.register_plugin("n0")
        for i in range(1, 1000):
            counter.register_plugin(f"n{i}", parent_id=f"n{(i - 1) // 10}")

        def build_tree_view():
            nodes = [n.to_snapshot() for n in counter.all_nodes()]
            topology: dict[str, None | str] = {}
            for n in counter.all_nodes():
                topology[n.plugin_id] = n.parent.plugin_id if n.parent else None
            return nodes, topology

        # 预热
        for _ in range(10):
            build_tree_view()

        iterations = 100
        start = time.perf_counter_ns()
        for _ in range(iterations):
            build_tree_view()
        elapsed_ns = time.perf_counter_ns() - start
        per_call_ms = elapsed_ns / iterations / 1_000_000

        assert per_call_ms <= 100, f"内省查询 {per_call_ms:.1f}ms > 100ms"
