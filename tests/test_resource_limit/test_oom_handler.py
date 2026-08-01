"""OOMHandler 单元测试 — 对应 tasks §5.4。"""


import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.resource_limit.oom_handler import OOMHandler
from src.core.resource_limit.resource_counter import ResourceCounter
from src.core.resource_limit.resource_limit_config import (
    FourTierLimit,
    ResourceLimitConfig,
    ResourceLimitConfigManager,
)
from src.core.resource_limit.types import OOMAction, ResourceDimension


class TestOOMHandler:
    """OOMHandler 核心功能。"""

    @pytest.fixture
    def setup(self):
        """搭建测试环境：2 插件 + 配置 + OOMHandler。"""
        config_mgr = ResourceLimitConfigManager()
        # 插件 a: min=10, max=100; 插件 b: min=50, max=200（硬保护）
        config_mgr.load_config("a", ResourceLimitConfig(
            "a", {ResourceDimension.TOKEN: FourTierLimit(10, 10, 50, 100)}
        ))
        config_mgr.load_config("b", ResourceLimitConfig(
            "b", {ResourceDimension.TOKEN: FourTierLimit(50, 50, 100, 200)}
        ))

        counter = ResourceCounter(max_limit_provider=config_mgr.get_max)
        counter.register_plugin("a")
        counter.register_plugin("b")

        kill_cb = MagicMock(return_value=True)
        handler = OOMHandler(
            resource_counter=counter,
            config_manager=config_mgr,
            event_bus=MagicMock(emit=AsyncMock()),
            service_manager=MagicMock(report_external_fault=AsyncMock()),
            kill_callback=kill_cb,
        )
        return counter, config_mgr, handler, kill_cb

    @pytest.mark.asyncio
    async def test_oom_lock_serial(self, setup):
        """两个并发 OOM 串行执行。"""
        counter, _, handler, _ = setup
        counter.charge("a", ResourceDimension.TOKEN, 80)
        # 同时触发两个 OOM
        results = await asyncio.gather(
            handler.trigger_oom("a", ResourceDimension.TOKEN, 150, 100),
            handler.trigger_oom("a", ResourceDimension.TOKEN, 150, 100),
        )
        # 两个都应返回决策（串行执行）
        assert all(r is not None for r in results)

    @pytest.mark.asyncio
    async def test_victim_selection_max_usage(self, setup):
        """选消耗最大者为受害者。"""
        counter, _, handler, _ = setup
        # a 用量 80，b 用量 30
        counter.charge("a", ResourceDimension.TOKEN, 80)
        counter.charge("b", ResourceDimension.TOKEN, 30)
        decision = await handler.trigger_oom("trigger", ResourceDimension.TOKEN, 150, 100)
        assert decision is not None
        assert decision.victim_plugin_id == "a"

    @pytest.mark.asyncio
    async def test_victim_skip_min_protected(self, setup):
        """跳过 usage < min 的硬保护插件。"""
        counter, _, handler, _ = setup
        # a 用量 80，b 用量 40（b 的 min=50，受保护）
        counter.charge("a", ResourceDimension.TOKEN, 80)
        counter.charge("b", ResourceDimension.TOKEN, 40)
        decision = await handler.trigger_oom("trigger", ResourceDimension.TOKEN, 150, 100)
        assert decision is not None
        assert decision.victim_plugin_id == "a"  # b 受保护被跳过

    @pytest.mark.asyncio
    async def test_no_victim_all_protected(self, setup):
        """全受保护时返回 None。"""
        counter, _, handler, _ = setup
        # 两个都低于 min（默认用量 0，不 charge）
        decision = await handler.trigger_oom("trigger", ResourceDimension.TOKEN, 150, 100)
        assert decision is None

    @pytest.mark.asyncio
    async def test_oom_action_is_kill(self, setup):
        """首版 OOM 动作为 KILL。"""
        counter, _, handler, _ = setup
        counter.charge("a", ResourceDimension.TOKEN, 80)
        decision = await handler.trigger_oom("trigger", ResourceDimension.TOKEN, 150, 100)
        assert decision.action == OOMAction.KILL

    @pytest.mark.asyncio
    async def test_oom_history_recorded(self, setup):
        """OOM 决策记录到历史。"""
        counter, _, handler, _ = setup
        counter.charge("a", ResourceDimension.TOKEN, 80)
        await handler.trigger_oom("trigger", ResourceDimension.TOKEN, 150, 100)
        # 等待异步 reap worker
        await asyncio.sleep(0.1)
        history = handler.get_oom_history()
        assert len(history) >= 1
        assert history[-1].victim_plugin_id == "a"