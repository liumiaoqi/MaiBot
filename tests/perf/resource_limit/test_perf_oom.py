"""OOM 性能测试 — 对应 tasks §10.1。

对标 spec §4.1 性能 3：OOM 触发到选定受害者 ≤ 50ms。
"""


import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.resource_limit.oom_handler import OOMHandler
from src.core.resource_limit.resource_counter import ResourceCounter
from src.core.resource_limit.resource_limit_config import (
    FourTierLimit,
    ResourceLimitConfig,
    ResourceLimitConfigManager,
)
from src.core.resource_limit.types import ResourceDimension


class TestPerfOOM:
    """OOM 决策性能。"""

    @pytest.mark.asyncio
    async def test_perf_oom_decision(self):
        """OOM 触发到选定受害者 ≤ 50ms。"""
        config_mgr = ResourceLimitConfigManager()
        config_mgr.load_config("a", ResourceLimitConfig(
            "a", {ResourceDimension.TOKEN: FourTierLimit(10, 10, 50, 100)}
        ))
        counter = ResourceCounter(max_limit_provider=config_mgr.get_max)
        counter.register_plugin("a")
        counter.charge("a", ResourceDimension.TOKEN, 80)

        handler = OOMHandler(
            resource_counter=counter,
            config_manager=config_mgr,
            event_bus=MagicMock(emit=AsyncMock()),
            service_manager=MagicMock(report_external_fault=AsyncMock()),
            kill_callback=MagicMock(return_value=True),
        )

        # 预热
        for _ in range(10):
            await handler.trigger_oom("trigger", ResourceDimension.TOKEN, 150, 100)
            await asyncio.sleep(0.01)

        iterations = 100
        start = time.perf_counter_ns()
        for _ in range(iterations):
            await handler.trigger_oom("trigger", ResourceDimension.TOKEN, 150, 100)
        elapsed_ns = time.perf_counter_ns() - start
        per_call_ms = elapsed_ns / iterations / 1_000_000

        assert per_call_ms <= 50, f"OOM 决策 {per_call_ms:.1f}ms > 50ms"