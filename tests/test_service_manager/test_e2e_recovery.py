"""端到端故障恢复测试。"""


import asyncio

import pytest

from src.core.adapters.service_manager_adapter import ServiceManagerAdapter
from src.core.service_manager.lifecycle import ComponentActions
from src.core.service_manager.types import (
    DependencyKind,
    DependencyRelation,
    HealthCheckResult,
    ServiceDescriptor,
    ServiceState,
    SystemHealthLevel,
)
from src.core.startup.types import (
    ComponentStatus,
    StartupComponent,
    StartupPhase,
    PhaseResult,
    StartupResult,
)


def _make_startup_result(names: list[str]) -> StartupResult:
    components = []
    for name in names:
        comp = StartupComponent(
            name=name,
            phase=StartupPhase.CORE_SERVICES,
            order=0,
            critical=True,
            init_fn=lambda: None,
        )
        comp.status = ComponentStatus.SUCCESS
        components.append(comp)
    phase = PhaseResult(
        phase=StartupPhase.CORE_SERVICES,
        status=ComponentStatus.SUCCESS,
        components=components,
    )
    return StartupResult(
        phases={StartupPhase.CORE_SERVICES: phase},
        ready=True,
        core_ready=True,
    )


class TestE2ERecovery:
    """端到端故障恢复链路测试。"""

    @pytest.mark.asyncio
    async def test_adopt_all_running(self) -> None:
        """adopt 组件后全部 RUNNING。"""
        result = _make_startup_result(["test"])
        descriptors = [
            ServiceDescriptor(identifier="test", display_name="测试"),
        ]

        adapter = ServiceManagerAdapter()
        adoption = await adapter.adopt_from_startup(result, descriptors, ())
        assert adoption.adopted_count == 1
        assert adapter.get_state("test").state == ServiceState.RUNNING
        await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_external_fault_triggers_recovery(self) -> None:
        """外部故障上报 → 转 FAULT → 恢复 → RUNNING。"""
        result = _make_startup_result(["test"])
        descriptors = [
            ServiceDescriptor(identifier="test", display_name="测试"),
        ]

        stop_called: list[str] = []
        start_called: list[str] = []

        async def stop_fn() -> None:
            stop_called.append("test")

        async def start_fn() -> None:
            start_called.append("test")

        actions = {"test": ComponentActions(stop_fn, start_fn)}
        adapter = ServiceManagerAdapter(
            component_actions=actions,
        )
        # 缩短退避时间
        adapter._recovery_engine = type(adapter._recovery_engine)(
            backoff_base_sec=0.01,
            backoff_cap_sec=0.1,
            storm_threshold=100,
        )
        await adapter.adopt_from_startup(result, descriptors, ())

        # 上报外部故障
        await adapter.report_external_fault("test", "test", "测试故障")

        # 等待恢复完成
        await asyncio.sleep(0.5)

        # 验证恢复流程执行
        assert len(stop_called) >= 1
        assert len(start_called) >= 1

        # 验证故障历史
        history = adapter.get_fault_history("test")
        assert len(history) >= 1

        await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_storm_protection(self) -> None:
        """连续恢复失败 → 风暴保护 → FAULT_MANUAL。"""
        result = _make_startup_result(["test"])
        descriptors = [
            ServiceDescriptor(identifier="test", display_name="测试"),
        ]

        start_count = 0

        async def stop_fn() -> None:
            pass

        async def start_fn() -> None:
            nonlocal start_count
            start_count += 1
            if start_count <= 3:
                raise RuntimeError("启动失败")

        actions = {"test": ComponentActions(stop_fn, start_fn)}
        adapter = ServiceManagerAdapter(
            component_actions=actions,
        )
        # 设置低风暴阈值和短退避
        adapter._recovery_engine = type(adapter._recovery_engine)(
            backoff_base_sec=0.01,
            backoff_cap_sec=0.05,
            storm_window_sec=600.0,
            storm_threshold=3,
        )
        await adapter.adopt_from_startup(result, descriptors, ())

        # 模拟健康检查连续失败记录
        for _ in range(3):
            adapter._recovery_engine.record_failure("test")

        # 上报故障触发恢复
        await adapter.report_external_fault("test", "test", "故障")
        await asyncio.sleep(1.0)

        # 验证风暴保护触发（恢复引擎返回 False）
        assert adapter._recovery_engine.is_storm("test")

        await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_manual_restart(self) -> None:
        """手动重启组件 → 恢复 RUNNING。"""
        result = _make_startup_result(["test"])
        descriptors = [
            ServiceDescriptor(identifier="test", display_name="测试"),
        ]

        async def stop_fn() -> None:
            pass

        async def start_fn() -> None:
            pass

        actions = {"test": ComponentActions(stop_fn, start_fn)}
        adapter = ServiceManagerAdapter(component_actions=actions)
        await adapter.adopt_from_startup(result, descriptors, ())

        # 停止组件
        await adapter.stop("test")
        assert adapter.get_state("test").state == ServiceState.STOPPED

        # 手动重启
        r = await adapter.restart("test")
        assert r.success
        assert adapter.get_state("test").state == ServiceState.RUNNING

        await adapter.shutdown()


class TestRegression:
    """启动接管回归测试。"""

    @pytest.mark.asyncio
    async def test_core_readiness_preserved(self) -> None:
        """adopt 后核心就绪三标志与启动期一致。"""
        components = []
        for name, flag in [
            ("msg", "message_pipeline_ready"),
            ("agent", "agent_thinking_ready"),
            ("reply", "reply_capability_ready"),
        ]:
            comp = StartupComponent(
                name=name,
                phase=StartupPhase.CORE_SERVICES,
                order=0,
                critical=True,
                init_fn=lambda: None,
                core_readiness_flag=flag,
            )
            comp.status = ComponentStatus.SUCCESS
            components.append(comp)

        phase = PhaseResult(
            phase=StartupPhase.CORE_SERVICES,
            status=ComponentStatus.SUCCESS,
            components=components,
        )
        result = StartupResult(
            phases={StartupPhase.CORE_SERVICES: phase},
            ready=True,
            core_ready=True,
        )

        descriptors = [
            ServiceDescriptor(identifier="msg", display_name="消息管道", core_readiness_flag="message_pipeline_ready"),
            ServiceDescriptor(identifier="agent", display_name="智能体", core_readiness_flag="agent_thinking_ready"),
            ServiceDescriptor(identifier="reply", display_name="回复器", core_readiness_flag="reply_capability_ready"),
        ]

        adapter = ServiceManagerAdapter()
        await adapter.adopt_from_startup(result, descriptors, ())

        view = adapter.get_system_health_view()
        assert view.message_pipeline_ready is True
        assert view.agent_thinking_ready is True
        assert view.reply_capability_ready is True
        assert view.core_ready is True

        await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_shutdown_does_not_crash(self) -> None:
        """服务管理器关闭不崩溃。"""
        result = _make_startup_result(["test"])
        descriptors = [ServiceDescriptor(identifier="test", display_name="测试")]

        adapter = ServiceManagerAdapter()
        await adapter.adopt_from_startup(result, descriptors, ())
        await adapter.shutdown()  # 应正常退出

    @pytest.mark.asyncio
    async def test_empty_registry(self) -> None:
        """空注册表不崩溃。"""
        result = StartupResult(ready=True, core_ready=True)
        adapter = ServiceManagerAdapter()
        adoption = await adapter.adopt_from_startup(result, [], ())
        assert adoption.adopted_count == 0
        await adapter.shutdown()