"""状态聚合引擎单元测试。"""


from src.core.service_manager.state_aggregator import StateAggregator
from src.core.service_manager.types import (
    HealthCheckMode,
    ServiceState,
    ServiceStateSnapshot,
    SystemHealthLevel,
    SystemHealthView,
)


def _make_snapshot(
    identifier: str, state: ServiceState, flag: str = ""
) -> ServiceStateSnapshot:
    return ServiceStateSnapshot(
        identifier=identifier,
        display_name=identifier,
        state=state,
        health_mode=HealthCheckMode.ACTIVE_PROBE,
    )


CORE_MAP = {
    "msg": "message_pipeline_ready",
    "agent": "agent_thinking_ready",
    "reply": "reply_capability_ready",
}


class TestComputeLevel:
    """四等级计算规则测试。"""

    def test_all_running_healthy(self) -> None:
        registry = {
            "msg": _make_snapshot("msg", ServiceState.RUNNING),
            "agent": _make_snapshot("agent", ServiceState.RUNNING),
            "reply": _make_snapshot("reply", ServiceState.RUNNING),
        }
        agg = StateAggregator(registry, CORE_MAP)
        assert agg.compute_level() == SystemHealthLevel.HEALTHY

    def test_restarting_recovering(self) -> None:
        registry = {
            "msg": _make_snapshot("msg", ServiceState.RESTARTING),
            "agent": _make_snapshot("agent", ServiceState.RUNNING),
            "reply": _make_snapshot("reply", ServiceState.RUNNING),
        }
        agg = StateAggregator(registry, CORE_MAP)
        assert agg.compute_level() == SystemHealthLevel.RECOVERING

    def test_core_fault(self) -> None:
        registry = {
            "msg": _make_snapshot("msg", ServiceState.FAULT),
            "agent": _make_snapshot("agent", ServiceState.RUNNING),
            "reply": _make_snapshot("reply", ServiceState.RUNNING),
        }
        agg = StateAggregator(registry, CORE_MAP)
        assert agg.compute_level() == SystemHealthLevel.FAULT

    def test_core_fault_manual(self) -> None:
        registry = {
            "msg": _make_snapshot("msg", ServiceState.FAULT_MANUAL),
            "agent": _make_snapshot("agent", ServiceState.RUNNING),
            "reply": _make_snapshot("reply", ServiceState.RUNNING),
        }
        agg = StateAggregator(registry, CORE_MAP)
        assert agg.compute_level() == SystemHealthLevel.FAULT

    def test_non_core_fault_degraded(self) -> None:
        registry = {
            "msg": _make_snapshot("msg", ServiceState.RUNNING),
            "agent": _make_snapshot("agent", ServiceState.RUNNING),
            "reply": _make_snapshot("reply", ServiceState.RUNNING),
            "emoji": _make_snapshot("emoji", ServiceState.FAULT),
        }
        agg = StateAggregator(registry, CORE_MAP)
        assert agg.compute_level() == SystemHealthLevel.DEGRADED

    def test_degraded_state(self) -> None:
        registry = {
            "msg": _make_snapshot("msg", ServiceState.RUNNING),
            "agent": _make_snapshot("agent", ServiceState.RUNNING),
            "reply": _make_snapshot("reply", ServiceState.RUNNING),
            "stat": _make_snapshot("stat", ServiceState.DEGRADED),
        }
        agg = StateAggregator(registry, CORE_MAP)
        assert agg.compute_level() == SystemHealthLevel.DEGRADED

    def test_restarting_takes_priority(self) -> None:
        """RECOVERING 优先于 FAULT。"""
        registry = {
            "msg": _make_snapshot("msg", ServiceState.RESTARTING),
            "agent": _make_snapshot("agent", ServiceState.FAULT),
            "reply": _make_snapshot("reply", ServiceState.RUNNING),
        }
        agg = StateAggregator(registry, CORE_MAP)
        assert agg.compute_level() == SystemHealthLevel.RECOVERING


class TestComputeCoreReadiness:
    """核心就绪重算测试。"""

    def test_all_running(self) -> None:
        registry = {
            "msg": _make_snapshot("msg", ServiceState.RUNNING),
            "agent": _make_snapshot("agent", ServiceState.RUNNING),
            "reply": _make_snapshot("reply", ServiceState.RUNNING),
        }
        agg = StateAggregator(registry, CORE_MAP)
        assert agg.compute_core_readiness() == (True, True, True)

    def test_one_fault(self) -> None:
        registry = {
            "msg": _make_snapshot("msg", ServiceState.FAULT),
            "agent": _make_snapshot("agent", ServiceState.RUNNING),
            "reply": _make_snapshot("reply", ServiceState.RUNNING),
        }
        agg = StateAggregator(registry, CORE_MAP)
        assert agg.compute_core_readiness() == (False, True, True)

    def test_all_fault(self) -> None:
        registry = {
            "msg": _make_snapshot("msg", ServiceState.FAULT),
            "agent": _make_snapshot("agent", ServiceState.FAULT),
            "reply": _make_snapshot("reply", ServiceState.FAULT),
        }
        agg = StateAggregator(registry, CORE_MAP)
        assert agg.compute_core_readiness() == (False, False, False)


class TestBuildView:
    """健康视图聚合测试。"""

    def test_view_fields(self) -> None:
        registry = {
            "msg": _make_snapshot("msg", ServiceState.RUNNING),
            "agent": _make_snapshot("agent", ServiceState.RUNNING),
            "reply": _make_snapshot("reply", ServiceState.RUNNING),
        }
        agg = StateAggregator(registry, CORE_MAP)
        view = agg.build_view()
        assert view.level == SystemHealthLevel.HEALTHY
        assert view.core_ready is True
        assert view.message_pipeline_ready is True
        assert view.agent_thinking_ready is True
        assert view.reply_capability_ready is True
        assert len(view.component_states) == 3
        assert view.degraded_components == []
        assert view.generated_at > 0

    def test_degraded_components_list(self) -> None:
        registry = {
            "msg": _make_snapshot("msg", ServiceState.RUNNING),
            "agent": _make_snapshot("agent", ServiceState.RUNNING),
            "reply": _make_snapshot("reply", ServiceState.RUNNING),
            "stat": _make_snapshot("stat", ServiceState.DEGRADED),
            "emoji": _make_snapshot("emoji", ServiceState.FAULT),
        }
        agg = StateAggregator(registry, CORE_MAP)
        view = agg.build_view()
        assert set(view.degraded_components) == {"stat", "emoji"}


class TestSubscribe:
    """事件推送测试。"""

    def test_level_change_triggers_callback(self) -> None:
        registry = {
            "msg": _make_snapshot("msg", ServiceState.RUNNING),
            "agent": _make_snapshot("agent", ServiceState.RUNNING),
            "reply": _make_snapshot("reply", ServiceState.RUNNING),
        }
        agg = StateAggregator(registry, CORE_MAP)

        received: list[SystemHealthView] = []
        agg.subscribe(lambda v: received.append(v))

        # 变更注册表状态使等级变化
        old_level = agg.compute_level()
        registry["msg"] = _make_snapshot("msg", ServiceState.FAULT)
        new_level = agg.compute_level()

        agg.check_and_notify(old_level, new_level)
        assert len(received) == 1
        assert received[0].level == SystemHealthLevel.FAULT

    def test_no_change_no_callback(self) -> None:
        registry = {
            "msg": _make_snapshot("msg", ServiceState.RUNNING),
        }
        agg = StateAggregator(registry, {})

        received: list[SystemHealthView] = []
        agg.subscribe(lambda v: received.append(v))

        agg.check_and_notify(
            SystemHealthLevel.HEALTHY, SystemHealthLevel.HEALTHY
        )
        assert len(received) == 0

    def test_subscriber_exception_does_not_crash(self) -> None:
        registry = {
            "msg": _make_snapshot("msg", ServiceState.RUNNING),
        }
        agg = StateAggregator(registry, {})

        def bad_callback(_v: SystemHealthView) -> None:
            raise RuntimeError("故意异常")

        received: list[SystemHealthView] = []
        agg.subscribe(bad_callback)
        agg.subscribe(lambda v: received.append(v))

        agg.check_and_notify(
            SystemHealthLevel.HEALTHY, SystemHealthLevel.DEGRADED
        )
        # 异常回调被跳过，正常回调仍执行
        assert len(received) == 1

    def test_unsubscribe(self) -> None:
        registry = {
            "msg": _make_snapshot("msg", ServiceState.RUNNING),
        }
        agg = StateAggregator(registry, {})

        received: list[SystemHealthView] = []

        def cb(v):
            received.append(v)

        agg.subscribe(cb)
        agg.unsubscribe(cb)

        agg.check_and_notify(
            SystemHealthLevel.HEALTHY, SystemHealthLevel.DEGRADED
        )
        assert len(received) == 0
