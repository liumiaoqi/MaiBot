"""故障恢复引擎单元测试。"""


import asyncio

import pytest

from src.core.service_manager.recovery import RecoveryEngine
from src.core.service_manager.types import ServiceDescriptor


class TestComputeBackoff:
    """指数退避计算测试。"""

    def test_base(self) -> None:
        r = RecoveryEngine(backoff_base_sec=1.0, backoff_cap_sec=300.0)
        assert r.compute_backoff(0) == 1.0

    def test_exponential(self) -> None:
        r = RecoveryEngine(backoff_base_sec=1.0, backoff_cap_sec=300.0)
        assert r.compute_backoff(1) == 2.0
        assert r.compute_backoff(2) == 4.0
        assert r.compute_backoff(3) == 8.0

    def test_cap(self) -> None:
        r = RecoveryEngine(backoff_base_sec=1.0, backoff_cap_sec=300.0)
        assert r.compute_backoff(10) == 300.0
        assert r.compute_backoff(100) == 300.0

    def test_custom_base(self) -> None:
        r = RecoveryEngine(backoff_base_sec=2.0, backoff_cap_sec=60.0)
        assert r.compute_backoff(0) == 2.0
        assert r.compute_backoff(2) == 8.0
        assert r.compute_backoff(10) == 60.0


class TestStormDetection:
    """滑动窗口风暴检测测试。"""

    def test_no_failures(self) -> None:
        r = RecoveryEngine(storm_threshold=5)
        assert r.is_storm("test") is False

    def test_below_threshold(self) -> None:
        r = RecoveryEngine(storm_threshold=5)
        for _ in range(4):
            r.record_failure("test")
        assert r.is_storm("test") is False

    def test_at_threshold(self) -> None:
        r = RecoveryEngine(storm_threshold=5)
        for _ in range(5):
            r.record_failure("test")
        assert r.is_storm("test") is True

    def test_reset_count(self) -> None:
        r = RecoveryEngine(storm_threshold=5)
        for _ in range(5):
            r.record_failure("test")
        assert r.is_storm("test") is True
        r.reset_count("test")
        assert r.is_storm("test") is False

    def test_different_components_independent(self) -> None:
        r = RecoveryEngine(storm_threshold=3)
        for _ in range(3):
            r.record_failure("a")
        assert r.is_storm("a") is True
        assert r.is_storm("b") is False


class TestRecoverFlow:
    """恢复流程编排测试。"""

    @pytest.mark.asyncio
    async def test_storm_returns_false(self) -> None:
        """风暴保护触发时返回 False。"""
        r = RecoveryEngine(
            backoff_base_sec=0.01,
            storm_threshold=3,
        )
        for _ in range(3):
            r.record_failure("test")

        # mock lifecycle_manager
        class MockLM:
            stop_called = False
            start_called = False

            async def stop(self, *args, **kwargs):
                MockLM.stop_called = True

            async def start(self, *args, **kwargs):
                MockLM.start_called = True

        result = await r.recover("test", MockLM())
        assert result is False
        assert MockLM.stop_called is False
        assert MockLM.start_called is False

    @pytest.mark.asyncio
    async def test_normal_recovery(self) -> None:
        """正常恢复流程调用 stop 和 start。"""
        r = RecoveryEngine(
            backoff_base_sec=0.01,
            backoff_cap_sec=0.1,
            storm_threshold=100,
        )

        class MockLM:
            def __init__(self):
                self.stop_called = False
                self.start_called = False

            async def stop(self, *args, **kwargs):
                self.stop_called = True

            async def start(self, *args, **kwargs):
                self.start_called = True

        lm = MockLM()
        result = await r.recover("test", lm)
        assert result is True
        assert lm.stop_called is True
        assert lm.start_called is True

    @pytest.mark.asyncio
    async def test_cancel_recovery(self) -> None:
        """手动操作取消自动恢复。"""
        r = RecoveryEngine(
            backoff_base_sec=1.0,
            backoff_cap_sec=1.0,
            storm_threshold=100,
        )

        class MockLM:
            async def stop(self, *args, **kwargs):
                pass

            async def start(self, *args, **kwargs):
                pass

        # 启动恢复，然后在退避期间取消
        lm = MockLM()
        task = asyncio.create_task(r.recover("test", lm))

        await asyncio.sleep(0.01)
        r.cancel_recovery("test")

        result = await task
        assert result is True  # 被取消也算执行完成
        assert r.get_backoff_count("test") == 0  # 重置了计数