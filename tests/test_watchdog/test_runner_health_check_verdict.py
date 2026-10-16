"""`watchdog.runner_health` 的判据——**针对"读类型上不存在的字段"这个缺陷**。

背景（2026-10-16 真机实测）：该检查原先读 `getattr(s, "is_healthy", None)`，而 `RunnerBridgeStatus`
没有 `is_healthy` 字段 ⇒ 恒 None ⇒ 每个 runner 恒判 unhealthy ⇒ **聚合健康永久 DOWN**
（容器里实测 `{"healthy": 0, "unhealthy": 3}`，而三个 runner 中 napcat 明明在转发日志）。

⇒ 本测试用**真实的 `RunnerBridgeStatus` 实例**（不是 Mock）来钉：健康的 runner 必须判 UP。
   如果将来有人再往检查器里塞一个类型上不存在的字段，这里会红。
"""

import pytest

from src.core.health_check import HealthStatus
from src.core.health_checks.watchdog_runner_health import WatchdogRunnerHealthCheck
from src.core.watchdog.types import DetectionSource, RunnerBridgeStatus


def _status(runner_id: str, *, failures: int = 0, recovering: bool = False) -> RunnerBridgeStatus:
    """按 `runner_health_bridge.py` 的两处构造点造状态：新注册/恢复后 failures=0、cooldown=0。"""
    return RunnerBridgeStatus(
        runner_id=runner_id,
        component_id=f"plugin_run_{runner_id}",
        last_detection_source=DetectionSource.HEARTBEAT,
        last_consecutive_failures=failures,
        cooldown_until=0.0,
        total_report_count=0,
        last_report_time=0.0,
        is_recovering=recovering,
    )


class _StubPort:
    def __init__(self, statuses: list[RunnerBridgeStatus]) -> None:
        self._statuses = statuses

    def list_runner_bridge_status(self) -> list[RunnerBridgeStatus]:
        return list(self._statuses)


@pytest.fixture
def _patch_port(monkeypatch):  # noqa: ANN001 —— pytest fixture
    import src.core.watchdog_port_registry as registry

    def _install(statuses: list[RunnerBridgeStatus]) -> None:
        monkeypatch.setattr(registry, "get_watchdog_port", lambda: _StubPort(statuses), raising=False)

    return _install


def test_type_has_no_is_healthy_field() -> None:
    """防腐层：本检查**不得**依赖 `is_healthy`——那个字段不存在（这就是缺陷的根因）。"""
    assert not hasattr(RunnerBridgeStatus, "is_healthy"), (
        "RunnerBridgeStatus 现在有 is_healthy 了？那请回头把检查器与本节一起改（并删本条）"
    )


@pytest.mark.asyncio
async def test_all_healthy_runners_report_up(_patch_port) -> None:  # noqa: ANN001
    """三只都健康（新注册基线：failures=0、不在恢复）⇒ 必须 UP（原先恒 DOWN）。"""
    _patch_port([_status("a"), _status("b"), _status("c")])

    result = await WatchdogRunnerHealthCheck().check()

    assert result.status is HealthStatus.UP, result
    assert result.details["healthy"] == 3 and result.details["unhealthy"] == 0, result.details


@pytest.mark.asyncio
async def test_one_failing_runner_degrades(_patch_port) -> None:  # noqa: ANN001
    """一只在故障中 ⇒ DEGRADED，且**点名**是哪一只。"""
    _patch_port([_status("ok"), _status("bad", failures=2)])

    result = await WatchdogRunnerHealthCheck().check()

    assert result.status is HealthStatus.DEGRADED, result
    assert result.details["unhealthy_runners"] == ["bad"], result.details


@pytest.mark.asyncio
async def test_all_failing_runners_report_down(_patch_port) -> None:  # noqa: ANN001
    """三只都在故障中 ⇒ DOWN（这条才是真正的 DOWN，不是原先那种恒 DOWN）。"""
    _patch_port([_status("a", failures=1), _status("b", failures=3), _status("c", failures=1)])

    result = await WatchdogRunnerHealthCheck().check()

    assert result.status is HealthStatus.DOWN, result
    assert len(result.details["unhealthy_runners"]) == 3, result.details


@pytest.mark.asyncio
async def test_recovering_runner_counts_unhealthy(_patch_port) -> None:  # noqa: ANN001
    """恢复中的 runner 算不健康（bridge 的 is_recovering 是独立信号）。"""
    _patch_port([_status("ok"), _status("rec", recovering=True)])

    result = await WatchdogRunnerHealthCheck().check()

    assert result.status is HealthStatus.DEGRADED, result
    assert result.details["unhealthy_runners"] == ["rec"], result.details
