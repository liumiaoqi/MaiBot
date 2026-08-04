"""StartupOrchestrator 波次调度执行测试（ZG-10 T17/T42/T43）。"""

import asyncio

import pytest

from src.core.startup.declaration import StartupItemDesc
from src.core.startup.orchestrator import StartupOrchestrator
from src.core.startup.types import StartupPhase


def _desc(name: str, phase: StartupPhase, init_fn=None, **kw) -> StartupItemDesc:
    async def _noop() -> None:
        return None

    return StartupItemDesc(name=name, phase=phase, init_fn=init_fn or _noop, **kw)


class TestRunBasic:
    @pytest.mark.asyncio
    async def test_run_success_ready(self) -> None:
        """正常启动：全部组件 SUCCESS，ready=True，wave_info 完整。"""
        orch = StartupOrchestrator()
        orch.register(_desc("a", StartupPhase.CORE_SERVICES, critical=True))
        orch.register(_desc("b", StartupPhase.READY, depends_on=["a"]))
        result = await orch.run()
        assert result.ready is True
        assert result.failed_components == []
        assert result.skipped_components == []
        # wave_info 包含相位
        assert StartupPhase.CORE_SERVICES in result.wave_info
        assert StartupPhase.READY in result.wave_info

    @pytest.mark.asyncio
    async def test_wave_parallel_execution(self) -> None:
        """同波次并行：两个 0.1s 组件总耗时 < 0.15s（并行非串行）。"""

        async def slow() -> None:
            await asyncio.sleep(0.1)

        orch = StartupOrchestrator()
        orch.register(_desc("x", StartupPhase.CORE_SERVICES, init_fn=slow))
        orch.register(_desc("y", StartupPhase.CORE_SERVICES, init_fn=slow))
        import time

        start = time.monotonic()
        await orch.run()
        elapsed = time.monotonic() - start
        assert elapsed < 0.15  # 串行需 0.2s，并行约 0.1s

    @pytest.mark.asyncio
    async def test_dependency_wave_order(self) -> None:
        """依赖序：B 依赖 A → A 先于 B 执行。"""
        order: list[str] = []

        async def init_a() -> None:
            order.append("a")

        async def init_b() -> None:
            order.append("b")

        orch = StartupOrchestrator()
        orch.register(_desc("b", StartupPhase.CORE_SERVICES, init_fn=init_b, depends_on=["a"]))
        orch.register(_desc("a", StartupPhase.CORE_SERVICES, init_fn=init_a))
        await orch.run()
        assert order == ["a", "b"]


class TestFailure:
    @pytest.mark.asyncio
    async def test_critical_failure_aborts_later_phases(self) -> None:
        """critical 失败 → 后续相位项 SKIPPED。"""
        async def boom() -> None:
            raise RuntimeError("init failed")

        orch = StartupOrchestrator()
        orch.register(_desc("bad", StartupPhase.CORE_SERVICES, init_fn=boom, critical=True))
        orch.register(_desc("later", StartupPhase.READY))
        result = await orch.run()
        assert result.ready is False
        assert "bad" in result.failed_components
        assert "later" in result.skipped_components

    @pytest.mark.asyncio
    async def test_strong_dependent_skipped(self) -> None:
        """失败传播：STRONG 依赖方 SKIPPED + failure_chains 记录。"""
        async def boom() -> None:
            raise RuntimeError("boom")

        orch = StartupOrchestrator()
        orch.register(_desc("bad", StartupPhase.CORE_SERVICES, init_fn=boom))
        orch.register(_desc(
            "dep", StartupPhase.CORE_SERVICES, depends_on=["bad"],
        ))
        result = await orch.run()
        # dep 在 bad 之后波次，bad 失败 → dep 被传播 SKIPPED
        assert "dep" in result.skipped_components
        assert result.failure_chains.get("dep") == "bad"

    @pytest.mark.asyncio
    async def test_weak_dependent_degraded(self) -> None:
        """失败传播：WEAK 依赖方 DEGRADED。"""
        from src.core.service_manager.types import DependencyKind

        async def boom() -> None:
            raise RuntimeError("boom")

        orch = StartupOrchestrator()
        orch.register(_desc("bad", StartupPhase.CORE_SERVICES, init_fn=boom))
        orch.register(_desc(
            "weak", StartupPhase.CORE_SERVICES, depends_on=["bad"],
            dependency_kind={"bad": DependencyKind.WEAK},
        ))
        result = await orch.run()
        assert "weak" in result.degraded_components

    @pytest.mark.asyncio
    async def test_barrier_gates_ready_phase(self) -> None:
        """核心就绪屏障：贡献组件失败 → READY 相位中止。"""
        async def boom() -> None:
            raise RuntimeError("boom")

        orch = StartupOrchestrator()
        orch.register(_desc(
            "chat_manager_adapter", StartupPhase.CORE_SERVICES,
            init_fn=boom, critical=True, core_readiness_flag="message_pipeline_ready",
        ))
        orch.register(_desc("message_handlers", StartupPhase.READY))
        result = await orch.run()
        # chat_manager_adapter 失败 → 相位中止 → READY 被 SKIPPED
        assert "message_handlers" in result.skipped_components


class TestSkipAndDebug:
    @pytest.mark.asyncio
    async def test_skip_names_excluded(self) -> None:
        """--skip-startup-item：跳过项 SKIPPED 不出现在执行。"""
        orch = StartupOrchestrator(skip_names={"b"})
        orch.register(_desc("a", StartupPhase.CORE_SERVICES, critical=True))
        orch.register(_desc("b", StartupPhase.CORE_SERVICES))
        result = await orch.run()
        assert "b" in result.skipped_components
        assert "a" not in result.skipped_components

    @pytest.mark.asyncio
    async def test_debug_mode_logs_items(self) -> None:
        """--debug-startup：逐项日志输出。"""
        from unittest.mock import patch

        orch = StartupOrchestrator(debug_mode=True)
        orch.register(_desc("a", StartupPhase.CORE_SERVICES))
        with patch("src.core.startup.orchestrator.logger") as mock_logger:
            await orch.run()
        assert any(
            "启动项 a" in (c.args[0] if c.args else "")
            for c in mock_logger.info.call_args_list
        )


class TestConfigFreeze:
    @pytest.mark.asyncio
    async def test_freeze_blocks_reload(self) -> None:
        """配置冻结后 reload_config 抛 ConfigFrozenError。"""
        from src.config.config import ConfigFrozenError, ConfigManager

        cm = ConfigManager()
        cm.freeze()
        assert cm.frozen is True
        with pytest.raises(ConfigFrozenError):
            await cm.reload_config()
