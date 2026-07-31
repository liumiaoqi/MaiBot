"""适配器衔接集成测试（ZG-6 Task 11）。

覆盖：启动完成（AC-INT-01）、健康变更驱动迁移（AC-INT-02）、CoreReadiness
衔接（AC-INT-03）、ZG-2 provider 注册（AC-INT-04）、ServiceManager 查询
（AC-INT-05）、BOOTING/SHUTTING_DOWN 谓词（AC-LIFE-04/05）、崩溃导出
（AC-LIFE-06）、无 loop 同步回退（实施提示 1）。
"""

import asyncio
import json

import pytest

from src.common.log_pipeline.suppressor import _get_current_health_level, set_health_level_provider
from src.core.adapters.core_readiness_port import CoreReadinessPortAdapter
from src.core.adapters.system_lifecycle_adapter import SystemLifecycleAdapter
from src.core.service_manager.state_aggregator import StateAggregator
from src.core.service_manager.types import (
    HealthCheckMode,
    ServiceState,
    ServiceStateSnapshot,
)
from src.core.startup.types import CoreReadiness
from src.core.system_state.state_machine import SystemStateMachine
from src.core.system_state.types import SystemLifecycleState


@pytest.fixture(autouse=True)
def _reset_health_provider():
    """每个测试后清空 ZG-2 健康 provider，避免跨测试泄漏。"""
    yield
    set_health_level_provider(None)


def _snapshot(identifier: str, state: ServiceState) -> ServiceStateSnapshot:
    return ServiceStateSnapshot(
        identifier=identifier,
        display_name=identifier,
        state=state,
        health_mode=HealthCheckMode.PASSIVE_HEARTBEAT,
    )


def _build_aggregator(state: ServiceState = ServiceState.RUNNING) -> StateAggregator:
    """三核心就绪贡献组件齐全（对齐生产 map，compute_core_readiness 可测恢复）。"""
    return StateAggregator(
        component_registry={
            "chat": _snapshot("chat", state),
            "agent": _snapshot("agent", state),
            "reply": _snapshot("reply", state),
        },
        core_readiness_map={
            "chat": "message_pipeline_ready",
            "agent": "agent_thinking_ready",
            "reply": "reply_capability_ready",
        },
    )


def _build_adapter(
    crash_export_dir=None,
    aggregator: StateAggregator | None = None,
) -> tuple[SystemStateMachine, CoreReadinessPortAdapter, StateAggregator, SystemLifecycleAdapter]:
    sm = SystemStateMachine()
    crp = CoreReadinessPortAdapter(CoreReadiness())
    agg = aggregator or _build_aggregator()
    adapter = SystemLifecycleAdapter(
        state_machine=sm,
        core_readiness_port=crp,
        state_aggregator=agg,
        crash_export_dir=crash_export_dir,
    )
    return sm, crp, agg, adapter


def _notify_level_change(agg: StateAggregator, new_state: ServiceState) -> None:
    """模拟 ServiceManagerAdapter._notify_level_change：先算旧等级，变更后算新等级并推送。"""
    old_level = agg.compute_level()
    agg._registry["chat"] = _snapshot("chat", new_state)
    new_level = agg.compute_level()
    agg.check_and_notify(old_level, new_level)


async def _wait_until(predicate, timeout: float = 1.0) -> None:
    """轮询等待条件成立（适配器桥接任务异步执行）。"""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("条件超时未成立")


async def test_startup_complete_to_ready():
    """AC-ZG6-INT-01-1: 正常启动完成 → READY。"""
    sm, crp, agg, adapter = _build_adapter()
    assert sm.is_booting()
    await adapter.trigger_startup_complete()
    assert sm.is_ready()
    assert adapter.is_running_like() is True
    assert sm.get_history()[-1].reason.value == "startup_complete"


async def test_startup_degraded_to_degrading():
    """W1: 降级启动完成 → DEGRADING。"""
    sm, crp, agg, adapter = _build_adapter()
    await adapter.trigger_startup_complete_degraded()
    assert sm.is_degrading()
    assert sm.get_history()[-1].reason.value == "startup_complete_degraded"


async def test_health_level_change_mapping():
    """AC-ZG6-INT-02-1~4: StateAggregator 健康变更经适配器驱动迁移。"""
    sm, crp, agg, adapter = _build_adapter()
    await adapter.trigger_startup_complete()  # READY

    # HEALTHY → DEGRADED（组件降级）→ READY→DEGRADING
    _notify_level_change(agg, ServiceState.DEGRADED)
    await _wait_until(lambda: sm.is_degrading())

    # DEGRADED → HEALTHY（组件恢复）→ DEGRADING→READY
    _notify_level_change(agg, ServiceState.RUNNING)
    await _wait_until(lambda: sm.is_ready())


async def test_health_level_change_fault_mapping():
    """AC-ZG6-INT-02: FAULT 等级（核心组件非 RUNNING）→ DEGRADING。"""
    aggregator = StateAggregator(
        component_registry={"chat": _snapshot("chat", ServiceState.RUNNING)},
        core_readiness_map={"chat": "message_pipeline_ready"},
    )
    sm, crp, agg, adapter = _build_adapter(aggregator=aggregator)
    await adapter.trigger_startup_complete()  # READY（初始 HEALTHY）

    # 核心就绪贡献组件离开 RUNNING → FAULT → DEGRADING
    _notify_level_change(agg, ServiceState.READY)
    await _wait_until(lambda: sm.is_degrading())


async def test_core_readiness_booting_false():
    """AC-ZG6-INT-03-1/2: BOOTING 全 False；READY 后按聚合器计算值恢复（CX 审查回归）。"""
    sm = SystemStateMachine()
    crp = CoreReadinessPortAdapter(CoreReadiness())
    # 模拟启动完成时三标志已置 True
    crp.update_flag("message_pipeline_ready", True)
    crp.update_flag("agent_thinking_ready", True)
    crp.update_flag("reply_capability_ready", True)
    agg = _build_aggregator()
    adapter = SystemLifecycleAdapter(state_machine=sm, core_readiness_port=crp, state_aggregator=agg)
    # trigger 前窗口：三标志全 False
    assert crp.get_core_readiness().message_pipeline_ready is False
    assert crp.get_core_readiness().agent_thinking_ready is False
    assert crp.get_core_readiness().reply_capability_ready is False
    # READY 后按聚合器恢复（三核心组件 RUNNING → 全 True）
    await adapter.trigger_startup_complete()
    cr = crp.get_core_readiness()
    assert cr.message_pipeline_ready is True
    assert cr.agent_thinking_ready is True
    assert cr.reply_capability_ready is True
    # 健康变更驱动持续同步：核心组件离开 RUNNING → 对应标志 False + 迁移 DEGRADING
    _notify_level_change(agg, ServiceState.READY)
    await _wait_until(lambda: sm.is_degrading())
    assert crp.get_core_readiness().message_pipeline_ready is False


async def test_zg2_provider_registered():
    """AC-ZG6-INT-04-1/2: ZG-2 provider 注册后日志抑制读取健康等级。"""
    try:
        _build_adapter()
        assert _get_current_health_level() == "healthy"
    finally:
        set_health_level_provider(None)


async def test_service_manager_query():
    """AC-ZG6-INT-05-1: ServiceManager 经适配器查询当前态。"""
    sm, crp, agg, adapter = _build_adapter()
    assert adapter.get_state() == SystemLifecycleState.BOOTING
    await adapter.trigger_startup_complete()
    assert adapter.get_state() == SystemLifecycleState.READY
    assert adapter.is_running_like() is True
    await adapter.trigger_shutdown()
    assert adapter.is_shutting_down() is True
    assert adapter.is_running_like() is False


async def test_booting_rejects_messages():
    """AC-ZG6-LIFE-04-1/2: BOOTING 期间 is_running_like False（消息管道拒收依据）。"""
    sm, crp, agg, adapter = _build_adapter()
    assert adapter.is_running_like() is False  # BOOTING：拒收
    assert adapter.is_booting() is True
    await adapter.trigger_startup_complete()
    assert adapter.is_running_like() is True  # READY：放行


async def test_shutting_down_predicate():
    """AC-ZG6-LIFE-05-1/2: SHUTTING_DOWN 期间行为约束。"""
    sm, crp, agg, adapter = _build_adapter()
    await adapter.trigger_startup_complete()
    await adapter.trigger_shutdown()
    assert adapter.is_shutting_down() is True
    assert adapter.is_running_like() is False


async def test_crash_export(tmp_path):
    """AC-ZG6-LIFE-06-1: 崩溃导出生成 lifecycle_*.log.jsonl 含迁移历史。"""
    sm, crp, agg, adapter = _build_adapter(crash_export_dir=tmp_path)
    await adapter.trigger_startup_complete()
    await adapter.trigger_shutdown()

    adapter._export_history("test-crash")
    files = list(tmp_path.glob("lifecycle_*.log.jsonl"))
    assert len(files) == 1
    lines = files[0].read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["old_state"] == "booting"
    assert json.loads(lines[-1])["new_state"] == "shutting_down"


async def test_crash_export_best_effort(tmp_path):
    """AC-ZG6-LIFE-06-2: 导出路径写入失败仅记录，不抛异常。"""
    sm, crp, agg, adapter = _build_adapter(crash_export_dir=tmp_path)
    await adapter.trigger_startup_complete()
    blocker = tmp_path / "not_a_dir"
    blocker.write_text("", encoding="utf-8")  # 占位文件，其下无法创建路径
    bad_path = blocker / "lifecycle_x.log.jsonl"
    adapter._export_history("test")  # 正常导出不受影响
    adapter._sm.export_history_to(bad_path)  # 失败路径 best-effort 不抛
    assert list(tmp_path.glob("lifecycle_*.log.jsonl"))


def test_create_task_no_loop_fallback():
    """实施提示 1: 无运行 loop 时同步回退触发迁移。"""
    # 同步上下文（无运行事件循环）：_main_loop 为 None，_on_health_view_change 走 asyncio.run
    sm = SystemStateMachine()
    crp = CoreReadinessPortAdapter(CoreReadiness())
    agg = _build_aggregator()
    adapter = SystemLifecycleAdapter(state_machine=sm, core_readiness_port=crp, state_aggregator=agg)
    asyncio.run(adapter.trigger_startup_complete())  # READY
    _notify_level_change(agg, ServiceState.DEGRADED)  # 无 loop → 同步回退完成迁移
    assert sm.is_degrading()
