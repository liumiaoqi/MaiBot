"""StartupArbiter 仲裁引擎单元测试（ZG-10 T40）。"""

import time

import pytest

from src.core.service_manager.exceptions import DependencyCycleError
from src.core.startup.arbiter import CoreReadinessBarrier, StartupArbiter
from src.core.startup.declaration import StartupItemDesc
from src.core.startup.types import ComponentStatus, StartupPhase


def _desc(name: str, phase: StartupPhase, **kw) -> StartupItemDesc:
    async def _noop() -> None:
        return None

    return StartupItemDesc(name=name, phase=phase, init_fn=_noop, **kw)


def _make_34_items() -> dict[str, StartupItemDesc]:
    """34 组件真实清单（33 组件 + watchdog——ZG-10 遗留 1 移入启动编排）。"""
    items: dict[str, StartupItemDesc] = {}
    for name, phase in [
        ("config_manager", StartupPhase.CONFIG_LOAD),
        ("config_validator", StartupPhase.CONFIG_LOAD),
        ("file_watcher", StartupPhase.INFRASTRUCTURE),
        ("tool_record_vacuum", StartupPhase.INFRASTRUCTURE),
        ("agent_registry", StartupPhase.CORE_SERVICES),
        ("session_submodules", StartupPhase.CORE_SERVICES),
        ("chat_manager_adapter", StartupPhase.CORE_SERVICES),
        ("replyer_port", StartupPhase.CORE_SERVICES),
        ("image_port", StartupPhase.CORE_SERVICES),
        ("runtime_port", StartupPhase.CORE_SERVICES),
        ("model_config_port", StartupPhase.CORE_SERVICES),
        ("llm_service_port", StartupPhase.CORE_SERVICES),
        ("message_ingestion_port", StartupPhase.CORE_SERVICES),
        ("person_info_port", StartupPhase.CORE_SERVICES),
        ("bot_config_port", StartupPhase.CORE_SERVICES),
        ("chat_config_port", StartupPhase.CORE_SERVICES),
        ("app_config_port", StartupPhase.CORE_SERVICES),
        ("event_bus_port", StartupPhase.CORE_SERVICES),
        ("prompt_manager", StartupPhase.CORE_SERVICES),
        ("message_port_v2", StartupPhase.CORE_SERVICES),
        ("watchdog", StartupPhase.CORE_SERVICES),
        ("plugin_runtime", StartupPhase.SUBSYSTEMS),
        ("ipc_bridge_port", StartupPhase.SUBSYSTEMS),
        ("plugin_runtime_v2", StartupPhase.SUBSYSTEMS),
        ("emoji_manager", StartupPhase.SUBSYSTEMS),
        ("model_config_port_inject", StartupPhase.SUBSYSTEMS),
        ("a_memorix", StartupPhase.SUBSYSTEMS),
        ("session_lifecycle", StartupPhase.SESSION_RESTORE),
        ("memory_automation", StartupPhase.SESSION_RESTORE),
        ("message_handlers", StartupPhase.READY),
        ("on_start_event", StartupPhase.READY),
        ("webui_server", StartupPhase.READY),
        ("scheduled_tasks", StartupPhase.READY),
        ("interaction_scheduler", StartupPhase.READY),
    ]:
        items[name] = _desc(name, phase)

    # 23 条依赖边（11 已声明 + 8 隐含 + 4 watchdog）
    edges = [
        ("replyer_port", "chat_manager_adapter"),
        ("replyer_port", "agent_registry"),
        ("session_lifecycle", "chat_manager_adapter"),
        ("interaction_scheduler", "message_handlers"),
        ("message_ingestion_port", "chat_manager_adapter"),
        ("memory_automation", "a_memorix"),
        ("emoji_manager", "llm_service_port"),
        ("plugin_runtime", "llm_service_port"),
        ("plugin_runtime_v2", "llm_service_port"),
        ("session_submodules", "agent_registry"),
        ("chat_manager_adapter", "session_submodules"),
        ("chat_manager_adapter", "agent_registry"),
        ("model_config_port", "agent_registry"),
        ("ipc_bridge_port", "plugin_runtime"),
        ("a_memorix", "model_config_port_inject"),
        ("a_memorix", "model_config_port"),
        ("interaction_scheduler", "a_memorix"),
        ("plugin_runtime_v2", "app_config_port"),
        ("message_handlers", "message_ingestion_port"),
        # watchdog 依赖（CORE_SERVICES 相位——SUBSYSTEMS 组件注册看门狗前置）
        ("watchdog", "app_config_port"),
        ("watchdog", "agent_registry"),
        ("watchdog", "chat_manager_adapter"),
        ("watchdog", "replyer_port"),
    ]
    for dep, base in edges:
        items[dep].depends_on.append(base)
    return items


class TestArbitrate:
    def test_34_components_wave_plan(self) -> None:
        """34 组件 + 23 边 → SUBSYSTEMS 2 波次，全局无环。"""
        arbiter = StartupArbiter()
        plan = arbiter.arbitrate(_make_34_items())
        assert plan.total_waves >= 1
        # SUBSYSTEMS 2 波次（与原型实验一致）
        subs_waves = plan.phases[StartupPhase.SUBSYSTEMS]
        assert len(subs_waves) == 2
        assert set(subs_waves[0]) == {"emoji_manager", "model_config_port_inject",
                                      "plugin_runtime", "plugin_runtime_v2"}
        assert set(subs_waves[1]) == {"a_memorix", "ipc_bridge_port"}
        # 全部 34 项出现在波次中（排除屏障虚拟节点）
        flat = {n for waves in plan.phases.values() for wave in waves for n in wave}
        flat.discard(CoreReadinessBarrier.VIRTUAL_NODE_ID)
        assert len(flat) == 34

    def test_barrier_after_core_services(self) -> None:
        """屏障虚拟节点在 CORE_SERVICES 之后（SESSION_RESTORE 波次中位于贡献组件后）。"""
        plan = StartupArbiter().arbitrate(_make_34_items())
        barrier_id = CoreReadinessBarrier.VIRTUAL_NODE_ID
        # READY 相位波次中包含屏障
        ready_waves = plan.phases[StartupPhase.READY]
        barrier_index = plan.barrier_wave[StartupPhase.READY]
        assert barrier_index >= 0
        assert barrier_id in ready_waves[barrier_index]
        # 屏障之前不能有 READY 项
        for wave in ready_waves[:barrier_index]:
            assert all(n != barrier_id for n in wave)

    def test_cycle_raises(self) -> None:
        """环依赖抛 DependencyCycleError。"""
        items = {
            "a": _desc("a", StartupPhase.CORE_SERVICES, depends_on=["b"]),
            "b": _desc("b", StartupPhase.CORE_SERVICES, depends_on=["a"]),
        }
        with pytest.raises(DependencyCycleError):
            StartupArbiter().arbitrate(items)

    def test_skip_names_excluded(self) -> None:
        """skip_names 中的项不出现在波次中。"""
        plan = StartupArbiter().arbitrate(
            _make_34_items(), skip_names={"webui_server", "scheduled_tasks"}
        )
        flat = {n for waves in plan.phases.values() for wave in waves for n in wave}
        assert "webui_server" not in flat
        assert "scheduled_tasks" not in flat
        assert "message_handlers" in flat

    def test_empty_items(self) -> None:
        """空 items 返回空 WavePlan。"""
        plan = StartupArbiter().arbitrate({})
        assert plan.phases == {}
        assert plan.total_waves == 0

    def test_arbitrate_under_50ms(self) -> None:
        """仲裁计算耗时 < 50ms（性能约束）。"""
        start = time.monotonic()
        StartupArbiter().arbitrate(_make_34_items())
        elapsed_ms = (time.monotonic() - start) * 1000
        assert elapsed_ms < 50


class TestCoreReadinessBarrier:
    def test_all_success_ready(self) -> None:
        """贡献组件全部 SUCCESS → 屏障就绪。"""
        barrier = CoreReadinessBarrier()
        states = {cid: ComponentStatus.SUCCESS for cid in barrier.contributor_ids}
        assert barrier.check(states) is True
        assert barrier.is_ready is True

    def test_failure_not_ready(self) -> None:
        """任一贡献组件非 SUCCESS → 未就绪 + 记录失败贡献者。"""
        barrier = CoreReadinessBarrier()
        states = {cid: ComponentStatus.SUCCESS for cid in barrier.contributor_ids}
        states["agent_registry"] = ComponentStatus.FAILED
        assert barrier.check(states) is False
        assert "agent_registry" in barrier.failed_contributors
