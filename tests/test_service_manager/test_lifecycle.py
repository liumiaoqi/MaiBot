"""生命周期管理引擎单元测试。"""


import asyncio

import pytest

from src.core.service_manager.dependency_graph import DependencyGraph
from src.core.service_manager.exceptions import (
    ConfirmationRequiredError,
    DependencyNotReadyError,
    RestartInProgressError,
    UnknownComponentError,
)
from src.core.service_manager.lifecycle import ComponentActions, LifecycleManager
from src.core.service_manager.types import (
    DependencyKind,
    DependencyRelation,
    HealthCheckMode,
    ServiceDescriptor,
    ServiceState,
    ServiceStateSnapshot,
)


def _make_snapshot(
    cid: str, state: ServiceState = ServiceState.RUNNING
) -> ServiceStateSnapshot:
    return ServiceStateSnapshot(
        identifier=cid,
        display_name=cid,
        state=state,
        health_mode=HealthCheckMode.ACTIVE_PROBE,
    )


def _make_descriptor(cid: str, flag: str = "") -> ServiceDescriptor:
    return ServiceDescriptor(
        identifier=cid, display_name=cid, core_readiness_flag=flag
    )


class TestStop:
    """停止操作测试。"""

    @pytest.mark.asyncio
    async def test_stop_unknown_component(self) -> None:
        registry: dict = {}
        lm = LifecycleManager(registry, {}, DependencyGraph(), {}, set())
        with pytest.raises(UnknownComponentError):
            await lm.stop("unknown")

    @pytest.mark.asyncio
    async def test_stop_restarting_raises(self) -> None:
        registry = {"test": _make_snapshot("test", ServiceState.RESTARTING)}
        lm = LifecycleManager(registry, {}, DependencyGraph(), {}, set())
        with pytest.raises(RestartInProgressError):
            await lm.stop("test")

    @pytest.mark.asyncio
    async def test_core_component_requires_confirmation(self) -> None:
        registry = {"msg": _make_snapshot("msg")}
        descriptors = {"msg": _make_descriptor("msg", "message_pipeline_ready")}
        lm = LifecycleManager(registry, descriptors, DependencyGraph(), {}, {"msg"})
        with pytest.raises(ConfirmationRequiredError):
            await lm.stop("msg")

    @pytest.mark.asyncio
    async def test_stop_with_confirmation(self) -> None:
        registry = {"msg": _make_snapshot("msg")}
        descriptors = {"msg": _make_descriptor("msg", "message_pipeline_ready")}
        stopped: list[str] = []

        async def stop_fn() -> None:
            stopped.append("msg")

        actions = {"msg": ComponentActions(stop_fn, lambda: asyncio.sleep(0))}
        lm = LifecycleManager(registry, descriptors, DependencyGraph(), actions, {"msg"})
        result = await lm.stop("msg", confirmed=True)
        assert result.success
        assert result.new_state == ServiceState.STOPPED
        assert registry["msg"].state == ServiceState.STOPPED

    @pytest.mark.asyncio
    async def test_cascade_stop_strong(self) -> None:
        """B 强依赖 A，停 A 时 B 级联停止。"""
        registry = {
            "A": _make_snapshot("A"),
            "B": _make_snapshot("B"),
        }
        g = DependencyGraph()
        g.add_relation(DependencyRelation("B", "A", DependencyKind.STRONG))

        stopped: list[str] = []

        async def stop_a() -> None:
            stopped.append("A")

        async def stop_b() -> None:
            stopped.append("B")

        actions = {
            "A": ComponentActions(stop_a, lambda: asyncio.sleep(0)),
            "B": ComponentActions(stop_b, lambda: asyncio.sleep(0)),
        }
        lm = LifecycleManager(registry, {}, g, actions, set())
        result = await lm.stop("A")
        assert result.success
        assert result.cascaded
        assert registry["A"].state == ServiceState.STOPPED
        assert registry["B"].state == ServiceState.STOPPED
        assert stopped.index("B") < stopped.index("A")  # B 先停

    @pytest.mark.asyncio
    async def test_cascade_stop_weak_degrades(self) -> None:
        """C 弱依赖 A，停 A 时 C 降级。"""
        registry = {
            "A": _make_snapshot("A"),
            "C": _make_snapshot("C"),
        }
        g = DependencyGraph()
        g.add_relation(DependencyRelation("C", "A", DependencyKind.WEAK))

        async def stop_a() -> None:
            pass

        actions = {"A": ComponentActions(stop_a, lambda: asyncio.sleep(0))}
        lm = LifecycleManager(registry, {}, g, actions, set())
        result = await lm.stop("A")
        assert result.success
        assert registry["A"].state == ServiceState.STOPPED
        assert registry["C"].state == ServiceState.DEGRADED


class TestStart:
    """启动操作测试。"""

    @pytest.mark.asyncio
    async def test_start_unknown_component(self) -> None:
        registry: dict = {}
        lm = LifecycleManager(registry, {}, DependencyGraph(), {}, set())
        with pytest.raises(UnknownComponentError):
            await lm.start("unknown")

    @pytest.mark.asyncio
    async def test_start_dependency_not_ready(self) -> None:
        """B 强依赖 A，A 已停止，启动 B 抛异常。"""
        registry = {
            "A": _make_snapshot("A", ServiceState.STOPPED),
            "B": _make_snapshot("B", ServiceState.STOPPED),
        }
        g = DependencyGraph()
        g.add_relation(DependencyRelation("B", "A", DependencyKind.STRONG))

        async def start_b() -> None:
            pass

        actions = {"B": ComponentActions(lambda: asyncio.sleep(0), start_b)}
        lm = LifecycleManager(registry, {}, g, actions, set())
        with pytest.raises(DependencyNotReadyError) as exc_info:
            await lm.start("B")
        assert "A" in exc_info.value.missing_dependencies

    @pytest.mark.asyncio
    async def test_start_success(self) -> None:
        registry = {"test": _make_snapshot("test", ServiceState.STOPPED)}
        started: list[str] = []

        async def start_fn() -> None:
            started.append("test")

        actions = {"test": ComponentActions(lambda: asyncio.sleep(0), start_fn)}
        lm = LifecycleManager(registry, {}, DependencyGraph(), actions, set())
        result = await lm.start("test")
        assert result.success
        assert result.new_state == ServiceState.RUNNING
        assert registry["test"].state == ServiceState.RUNNING

    @pytest.mark.asyncio
    async def test_start_with_weak_dep_fault_degrades(self) -> None:
        """B 弱依赖 A，A 故障，启动 B 成功但降级。"""
        registry = {
            "A": _make_snapshot("A", ServiceState.FAULT),
            "B": _make_snapshot("B", ServiceState.STOPPED),
        }
        g = DependencyGraph()
        g.add_relation(DependencyRelation("B", "A", DependencyKind.WEAK))

        async def start_b() -> None:
            pass

        actions = {"B": ComponentActions(lambda: asyncio.sleep(0), start_b)}
        lm = LifecycleManager(registry, {}, g, actions, set())
        result = await lm.start("B")
        assert result.success
        assert result.new_state == ServiceState.DEGRADED

    @pytest.mark.asyncio
    async def test_start_failure(self) -> None:
        registry = {"test": _make_snapshot("test", ServiceState.STOPPED)}

        async def bad_start() -> None:
            raise RuntimeError("启动失败")

        actions = {"test": ComponentActions(lambda: asyncio.sleep(0), bad_start)}
        lm = LifecycleManager(registry, {}, DependencyGraph(), actions, set())
        result = await lm.start("test")
        assert not result.success
        assert result.new_state == ServiceState.FAULT


class TestRestart:
    """重启操作测试。"""

    @pytest.mark.asyncio
    async def test_restart_restarting_raises(self) -> None:
        registry = {"test": _make_snapshot("test", ServiceState.RESTARTING)}
        lm = LifecycleManager(registry, {}, DependencyGraph(), {}, set())
        with pytest.raises(RestartInProgressError):
            await lm.restart("test")

    @pytest.mark.asyncio
    async def test_restart_success(self) -> None:
        registry = {"test": _make_snapshot("test")}

        async def stop_fn() -> None:
            pass

        async def start_fn() -> None:
            pass

        actions = {"test": ComponentActions(stop_fn, start_fn)}
        lm = LifecycleManager(registry, {}, DependencyGraph(), actions, set())
        result = await lm.restart("test")
        assert result.success
        assert result.new_state == ServiceState.RUNNING