"""ResourceEventPropagator 单元测试 — 对应 tasks §6.2。"""


import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.resource_limit.resource_counter import ResourceCounter
from src.core.resource_limit.resource_event_propagator import (
    ResourceEventPropagator,
)


class _RecordingBus:
    """记录所有 emit 调用的 event_bus 桩。"""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    async def emit(self, event_type: str, data: dict) -> None:
        self.calls.append((event_type, data))


class TestResourceEventPropagator:
    """ResourceEventPropagator 核心功能。"""

    @pytest.fixture
    def bus(self):
        return _RecordingBus()

    @pytest.fixture
    def propagator(self, bus):
        return ResourceEventPropagator(event_bus=bus, dedup_window_ms=50)

    @pytest.mark.asyncio
    async def test_propagate_single_node(self, propagator, bus):
        """单节点事件 emit 一次。"""
        await propagator.propagate("a", "resource.usage", {"v": 1})
        assert len(bus.calls) == 1
        assert bus.calls[0][0] == "resource.usage"
        assert bus.calls[0][1]["plugin_id"] == "a"

    @pytest.mark.asyncio
    async def test_propagate_parent_chain(self, propagator, bus):
        """父链向上传播：A→B→根，emit A，三个节点都收到。"""
        counter = ResourceCounter()
        counter.register_plugin("b")
        counter.register_plugin("a", parent_id="b")
        await propagator.propagate(
            "a", "resource.limit_exceeded", {"d": 1}, node_provider=counter
        )
        # 根 + b + a = 3 次
        assert len(bus.calls) == 3
        received_ids = [c[1]["plugin_id"] for c in bus.calls]
        assert "a" in received_ids
        assert "b" in received_ids

    @pytest.mark.asyncio
    async def test_local_only_restricts_to_current(self, propagator, bus):
        """local_only=True 仅当前节点 emit。"""
        counter = ResourceCounter()
        counter.register_plugin("b")
        counter.register_plugin("a", parent_id="b")
        await propagator.propagate(
            "a", "resource.usage", {"v": 1}, local_only=True, node_provider=counter
        )
        assert len(bus.calls) == 1
        assert bus.calls[0][1]["plugin_id"] == "a"

    @pytest.mark.asyncio
    async def test_config_events_local_restricts(self, bus):
        """config.is_events_local=True 时仅当前节点。"""
        config = MagicMock()
        config.is_events_local = MagicMock(return_value=True)
        prop = ResourceEventPropagator(event_bus=bus, config_manager=config)
        counter = ResourceCounter()
        counter.register_plugin("b")
        counter.register_plugin("a", parent_id="b")
        await prop.propagate(
            "a", "resource.usage", {"v": 1}, node_provider=counter
        )
        assert len(bus.calls) == 1

    @pytest.mark.asyncio
    async def test_dedup_within_window(self, propagator, bus):
        """去重窗口内重复事件被过滤。"""
        await propagator.propagate("a", "resource.usage", {"v": 1})
        await propagator.propagate("a", "resource.usage", {"v": 2})
        assert len(bus.calls) == 1

    @pytest.mark.asyncio
    async def test_dedup_across_window(self, propagator, bus):
        """去重窗口外事件通过。"""
        propagator._dedup_window_ms = 0  # 窗口为 0，立即放行
        await propagator.propagate("a", "resource.usage", {"v": 1})
        await propagator.propagate("a", "resource.usage", {"v": 2})
        assert len(bus.calls) == 2

    @pytest.mark.asyncio
    async def test_dedup_different_event_types(self, propagator, bus):
        """不同事件类型不去重。"""
        await propagator.propagate("a", "resource.usage", {"v": 1})
        await propagator.propagate("a", "resource.oom", {"v": 2})
        assert len(bus.calls) == 2

    @pytest.mark.asyncio
    async def test_depth_limit_truncates(self, bus):
        """深度超限截断并 warning。"""
        counter = ResourceCounter()
        # 构造 40 层链
        counter.register_plugin("n0")
        for i in range(1, 40):
            counter.register_plugin(f"n{i}", parent_id=f"n{i - 1}")
        prop = ResourceEventPropagator(event_bus=bus, max_depth=5)
        await prop.propagate(
            "n39", "resource.usage", {"v": 1}, node_provider=counter
        )
        assert len(bus.calls) <= 6  # max_depth=5 + 1

    @pytest.mark.asyncio
    async def test_emit_failure_continues(self, bus):
        """emit 失败时继续至下一节点。"""
        fail_bus = MagicMock()
        call_count = [0]

        async def _emit(event_type, data):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("boom")

        fail_bus.emit = _emit
        prop = ResourceEventPropagator(event_bus=fail_bus)
        counter = ResourceCounter()
        counter.register_plugin("b")
        counter.register_plugin("a", parent_id="b")
        await prop.propagate(
            "a", "resource.usage", {"v": 1}, node_provider=counter
        )
        # 第一次失败，后续继续
        assert call_count[0] >= 2

    @pytest.mark.asyncio
    async def test_no_node_provider_single_emit(self, propagator, bus):
        """node_provider=None 仅当前节点。"""
        await propagator.propagate("a", "resource.usage", {"v": 1})
        assert len(bus.calls) == 1

    @pytest.mark.asyncio
    async def test_clear_dedup_cache(self, propagator, bus):
        """clear_dedup_cache 后同事件可再次传播。"""
        await propagator.propagate("a", "resource.usage", {"v": 1})
        propagator.clear_dedup_cache()
        await propagator.propagate("a", "resource.usage", {"v": 2})
        assert len(bus.calls) == 2

    @pytest.mark.asyncio
    async def test_no_event_bus_silent(self):
        """event_bus=None 时静默不报错。"""
        prop = ResourceEventPropagator(event_bus=None)
        await prop.propagate("a", "resource.usage", {"v": 1})