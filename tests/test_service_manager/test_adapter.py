"""ServiceManagerAdapter 集成测试。"""


import asyncio

import pytest

from src.core.adapters.service_manager_adapter import ServiceManagerAdapter
from src.core.service_manager.exceptions import DependencyCycleError
from src.core.service_manager.lifecycle import ComponentActions
from src.core.service_manager.types import (
    DependencyKind,
    DependencyRelation,
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


def _make_component(
    name: str,
    status: ComponentStatus = ComponentStatus.SUCCESS,
    flag: str = "",
) -> StartupComponent:
    comp = StartupComponent(
        name=name,
        phase=StartupPhase.CORE_SERVICES,
        order=0,
        critical=True,
        init_fn=lambda: None,
        core_readiness_flag=flag,
    )
    comp.status = status
    return comp


def _make_startup_result(
    components: list[StartupComponent],
) -> StartupResult:
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


def _core_descriptors() -> list[ServiceDescriptor]:
    return [
        ServiceDescriptor(
            identifier="msg",
            display_name="消息管道",
            core_readiness_flag="message_pipeline_ready",
        ),
        ServiceDescriptor(
            identifier="agent",
            display_name="智能体",
            core_readiness_flag="agent_thinking_ready",
        ),
        ServiceDescriptor(
            identifier="reply",
            display_name="回复器",
            core_readiness_flag="reply_capability_ready",
        ),
        ServiceDescriptor(identifier="emoji", display_name="表情"),
    ]


def _core_dependencies() -> tuple[DependencyRelation, ...]:
    return (
        DependencyRelation("reply", "msg", DependencyKind.STRONG),
        DependencyRelation("reply", "agent", DependencyKind.STRONG),
        DependencyRelation("emoji", "agent", DependencyKind.WEAK),
    )


class TestAdoptFromStartup:
    """接管流程测试。"""

    @pytest.mark.asyncio
    async def test_full_adoption(self) -> None:
        components = [
            _make_component("msg", flag="message_pipeline_ready"),
            _make_component("agent", flag="agent_thinking_ready"),
            _make_component("reply", flag="reply_capability_ready"),
            _make_component("emoji"),
        ]
        result = _make_startup_result(components)

        adapter = ServiceManagerAdapter()
        adoption = await adapter.adopt_from_startup(
            result, _core_descriptors(), _core_dependencies()
        )
        assert adoption.adopted_count == 4
        assert adoption.skipped_count == 0
        assert adoption.dangling_dependencies == []
        await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_skips_failed_components(self) -> None:
        components = [
            _make_component("msg", flag="message_pipeline_ready"),
            _make_component("agent", flag="agent_thinking_ready"),
            _make_component("reply", flag="reply_capability_ready"),
            _make_component("emoji", status=ComponentStatus.FAILED),
        ]
        result = _make_startup_result(components)

        adapter = ServiceManagerAdapter()
        adoption = await adapter.adopt_from_startup(
            result, _core_descriptors(), _core_dependencies()
        )
        assert adoption.adopted_count == 3
        assert adoption.skipped_count == 1
        await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_dangling_dependencies(self) -> None:
        components = [
            _make_component("agent", flag="agent_thinking_ready"),
            _make_component("reply", flag="reply_capability_ready"),
        ]
        result = _make_startup_result(components)

        # msg 在依赖中但未启动 → 悬空
        deps = _core_dependencies()
        adapter = ServiceManagerAdapter()
        adoption = await adapter.adopt_from_startup(
            result, _core_descriptors(), deps
        )
        assert "msg" in adoption.dangling_dependencies
        await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_cycle_rejected(self) -> None:
        components = [_make_component("A"), _make_component("B")]
        result = _make_startup_result(components)

        descriptors = [
            ServiceDescriptor(identifier="A", display_name="A"),
            ServiceDescriptor(identifier="B", display_name="B"),
        ]
        deps = (
            DependencyRelation("A", "B", DependencyKind.STRONG),
            DependencyRelation("B", "A", DependencyKind.STRONG),
        )

        adapter = ServiceManagerAdapter()
        with pytest.raises(DependencyCycleError):
            await adapter.adopt_from_startup(result, descriptors, deps)


class TestStopStartThroughAdapter:
    """通过适配器执行 stop/start 测试。"""

    @pytest.mark.asyncio
    async def test_stop_cascades_and_notifies(self) -> None:
        components = [
            _make_component("msg", flag="message_pipeline_ready"),
            _make_component("agent", flag="agent_thinking_ready"),
            _make_component("reply", flag="reply_capability_ready"),
        ]
        result = _make_startup_result(components)

        stop_called: list[str] = []

        async def stop_msg() -> None:
            stop_called.append("msg")

        async def stop_reply() -> None:
            stop_called.append("reply")

        actions = {
            "msg": ComponentActions(stop_msg, lambda: asyncio.sleep(0)),
            "reply": ComponentActions(stop_reply, lambda: asyncio.sleep(0)),
        }
        adapter = ServiceManagerAdapter(component_actions=actions)
        await adapter.adopt_from_startup(
            result, _core_descriptors(), _core_dependencies()
        )

        # 订阅等级变更
        levels: list[SystemHealthLevel] = []
        adapter.subscribe_health_change(lambda v: levels.append(v.level))

        # 停止 msg（核心组件，需确认）
        r = await adapter.stop("msg", confirmed=True)
        assert r.success
        assert r.cascaded  # reply 级联停止

        # 验证状态
        assert adapter.get_state("msg").state == ServiceState.STOPPED
        assert adapter.get_state("reply").state == ServiceState.STOPPED

        # 验证等级变更通知
        assert len(levels) > 0
        assert levels[-1] == SystemHealthLevel.FAULT

        await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_start_dependency_check(self) -> None:
        components = [
            _make_component("msg", flag="message_pipeline_ready"),
            _make_component("agent", flag="agent_thinking_ready"),
            _make_component("reply", flag="reply_capability_ready"),
        ]
        result = _make_startup_result(components)

        adapter = ServiceManagerAdapter()
        await adapter.adopt_from_startup(
            result, _core_descriptors(), _core_dependencies()
        )

        # 先停止 msg
        await adapter.stop("msg", confirmed=True)
        assert adapter.get_state("msg").state == ServiceState.STOPPED

        # 启动 reply 应失败（依赖 msg 未就绪）
        from src.core.service_manager.exceptions import DependencyNotReadyError
        with pytest.raises(DependencyNotReadyError):
            await adapter.start("reply")

        await adapter.shutdown()


class TestHealthView:
    """系统健康视图测试。"""

    @pytest.mark.asyncio
    async def test_view_fields_complete(self) -> None:
        components = [
            _make_component("msg", flag="message_pipeline_ready"),
            _make_component("agent", flag="agent_thinking_ready"),
            _make_component("reply", flag="reply_capability_ready"),
            _make_component("emoji"),
        ]
        result = _make_startup_result(components)

        adapter = ServiceManagerAdapter()
        await adapter.adopt_from_startup(
            result, _core_descriptors(), _core_dependencies()
        )

        view = adapter.get_system_health_view()
        assert view.level == SystemHealthLevel.HEALTHY
        assert view.core_ready is True
        assert view.message_pipeline_ready is True
        assert view.agent_thinking_ready is True
        assert view.reply_capability_ready is True
        assert len(view.component_states) == 4
        assert view.degraded_components == []
        assert view.generated_at > 0

        await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_fault_history(self) -> None:
        components = [
            _make_component("msg", flag="message_pipeline_ready"),
            _make_component("agent", flag="agent_thinking_ready"),
            _make_component("reply", flag="reply_capability_ready"),
        ]
        result = _make_startup_result(components)

        adapter = ServiceManagerAdapter()
        await adapter.adopt_from_startup(
            result, _core_descriptors(), _core_dependencies()
        )

        # 上报外部故障
        await adapter.report_external_fault("msg", "test", "测试故障")

        history = adapter.get_fault_history("msg")
        assert len(history) == 1
        assert history[0].component_id == "msg"

        await adapter.shutdown()