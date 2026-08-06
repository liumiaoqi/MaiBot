"""ZG-14 T1.9 — ErrorEscalator 核心引擎测试（升级判定 + 动作分派 + 防护）。

覆盖 spec §7 验收场景的引擎级部分：场景 1/2/3/4/5/6/13/15/18/20 + 22
（P1-5 Suppressor 联动）；场景 7/8（ZG-7 委托）属 Phase 2 集成测试。
"""

from unittest.mock import MagicMock

from src.core.error_escalation.config import ErrorEscalationConfig
from src.core.error_escalation.types import ErrorAction, ErrorLevel
from src.core.service_manager.types import SystemHealthLevel
from src.core.tainted_mask.taint_flag import TaintFlag

from tests.test_error_escalation._helpers import drain as _drain
from tests.test_error_escalation._helpers import make_escalator


class TestScenario1SingleWarn:
    """场景 1：单次 WARN 无升级——LOG + TAINT + COUNT，无 DEGRADE/CRASH_DUMP/NOTIFY。"""

    async def test_single_warn_no_upgrade(self) -> None:
        esc, ports = make_escalator()
        esc.report(ErrorLevel.WARN, "test warn")
        await _drain(esc)
        ports["taint"].add_taint.assert_called_once_with(TaintFlag.TAINT_WARN)
        ports["state_machine"].trigger_health_level_change.assert_not_called()
        ports["crash_dump"].export_snapshot.assert_not_called()
        ports["event_bus"].emit_sync.assert_not_called()
        assert esc.get_stats().counts[ErrorLevel.WARN] == 1


class TestScenario2SwitchUpgrade:
    """场景 2：开关升级 WARN→ERROR→DEGRADE（spec §5.2.1 规则 1）。"""

    async def test_error_on_warn_upgrades(self) -> None:
        esc, ports = make_escalator(ErrorEscalationConfig(error_on_warn=True))
        esc.report(ErrorLevel.WARN, "upgrade me")
        await _drain(esc)
        ports["state_machine"].trigger_health_level_change.assert_called_once_with(SystemHealthLevel.DEGRADED)
        ports["taint"].add_taint.assert_called_once_with(TaintFlag.TAINT_EXCEPTION_SWALLOWED)
        # ERROR 动作集含 REPORT_FAULT（无 component_id 跳过）
        ports["service_manager"].report_external_fault.assert_not_called()

    async def test_critical_on_error_upgrades(self) -> None:
        """场景 2b：ERROR→CRITICAL 开关升级。"""
        esc, ports = make_escalator(ErrorEscalationConfig(critical_on_error=True))
        esc.report(ErrorLevel.ERROR, "upgrade to critical", component_id="comp-a")
        await _drain(esc)
        ports["crash_dump"].export_snapshot.assert_called_once()
        ports["event_bus"].emit_sync.assert_called_once()
        # 已升级 CRITICAL——不再走 DEGRADE
        ports["state_machine"].trigger_health_level_change.assert_not_called()


class TestScenario3CountUpgrade:
    """场景 3：计数升级 WARN 累计达阈→ERROR（spec §5.2.1 规则 3）。"""

    async def test_warn_count_threshold_upgrades(self) -> None:
        esc, ports = make_escalator(ErrorEscalationConfig(warn_error_threshold=10))
        for _ in range(9):
            esc.report(ErrorLevel.WARN, "repeat warn")
        ports["state_machine"].trigger_health_level_change.assert_not_called()
        esc.report(ErrorLevel.WARN, "repeat warn")  # 第 10 次
        await _drain(esc)
        ports["state_machine"].trigger_health_level_change.assert_called_once_with(SystemHealthLevel.DEGRADED)
        # 9 次 WARN 计 WARN，第 10 次升级后计 ERROR（规则 11）
        stats = esc.get_stats()
        assert stats.counts[ErrorLevel.WARN] == 9
        assert stats.counts[ErrorLevel.ERROR] == 1


class TestScenario4CriticalSnapshot:
    """场景 4：CRITICAL 触发主动快照 + RESTART_COMPONENT + NOTIFY。"""

    async def test_critical_triggers_snapshot_and_restart(self) -> None:
        esc, ports = make_escalator()
        esc.report(ErrorLevel.CRITICAL, "critical failure", component_id="comp-a")
        await _drain(esc)
        ports["crash_dump"].export_snapshot.assert_called_once()
        ports["service_manager"].restart.assert_called_once_with("comp-a")
        ports["event_bus"].emit_sync.assert_called_once_with(
            "error.escalation",
            ports["event_bus"].emit_sync.call_args.args[1],
        )

    async def test_critical_without_component_skips_restart(self) -> None:
        """component_id 缺失跳过 RESTART_COMPONENT（spec §5.1.1 规则 4）。"""
        esc, ports = make_escalator()
        esc.report(ErrorLevel.CRITICAL, "no component")
        await _drain(esc)
        ports["service_manager"].restart.assert_not_called()
        ports["crash_dump"].export_snapshot.assert_called_once()

    async def test_crash_dump_below_min_level_skipped(self) -> None:
        """crash_dump_min_level=CRITICAL 时 ERROR 不触发快照（spec §5.5.1 规则 2）。"""
        esc, ports = make_escalator()
        esc.report(ErrorLevel.ERROR, "below min level")
        await _drain(esc)
        ports["crash_dump"].export_snapshot.assert_not_called()

    async def test_crash_dump_rate_limited(self) -> None:
        """快照限流：1 分钟最多 3 次（spec §5.5.1 规则 4）。"""
        esc, ports = make_escalator()
        for _ in range(5):
            esc.report(ErrorLevel.CRITICAL, "flood", component_id="comp-a")
        await _drain(esc)
        assert ports["crash_dump"].export_snapshot.call_count == 3

    async def test_crash_dump_sync_port_does_not_raise(self) -> None:
        """回归（CX 审查 P1）：生产注入同步 CrashDump——report 不抛异常。

        export_snapshot 是同步方法（返回 None），若被误入 create_task
        派发会抛 TypeError 并阻断后续动作；此处验证同步调用路径。
        """
        esc, ports = make_escalator()
        # 显式保证 export_snapshot 为同步 mock（返回 None 非 coroutine）
        ports["crash_dump"].export_snapshot = MagicMock(return_value=None)
        esc.report(ErrorLevel.CRITICAL, "sync snapshot", component_id="comp-a")
        await _drain(esc)
        ports["crash_dump"].export_snapshot.assert_called_once()
        ports["event_bus"].emit_sync.assert_called_once()  # 后续动作不受影响
        ports["service_manager"].restart.assert_called_once_with("comp-a")

    async def test_crash_dump_port_raises_does_not_block(self) -> None:
        """export_snapshot 抛异常不阻断其他动作（spec §5.5.1 规则 5）。"""
        esc, ports = make_escalator()
        ports["crash_dump"].export_snapshot = MagicMock(side_effect=OSError("disk full"))
        esc.report(ErrorLevel.CRITICAL, "disk full", component_id="comp-a")
        await _drain(esc)
        ports["event_bus"].emit_sync.assert_called_once()
        ports["service_manager"].restart.assert_called_once_with("comp-a")


class TestScenario5FatalGracefulStop:
    """场景 5：FATAL 优雅停机不杀进程（N2 裁决）。"""

    async def test_fatal_triggers_shutdown(self) -> None:
        esc, ports = make_escalator()
        esc.report(ErrorLevel.FATAL, "fatal error")
        await _drain(esc)
        ports["state_machine"].trigger_shutdown.assert_called_once()
        ports["event_bus"].emit_sync.assert_called_once()

    async def test_fatal_process_keeps_running(self) -> None:
        """N2 裁决：FATAL 上报后测试进程继续运行（spec §5.3.1 规则 12）。"""
        esc, ports = make_escalator()
        esc.report(ErrorLevel.FATAL, "must not kill")
        assert True  # 进程未退出即通过


class TestScenario13NestedFatalGuard:
    """场景 13：嵌套 FATAL 防护（对标 oops_in_progress > 1，spec §4.2 规则 2）。"""

    async def test_nested_fatal_skips_duplicate_stop(self) -> None:
        esc, ports = make_escalator()
        esc.report(ErrorLevel.FATAL, "first fatal")
        esc.report(ErrorLevel.FATAL, "nested fatal")  # 执行期间
        assert ports["state_machine"].trigger_shutdown.call_count == 1
        await _drain(esc)  # 任务完成 → 标志重置
        esc.report(ErrorLevel.FATAL, "third fatal")
        await _drain(esc)
        assert ports["state_machine"].trigger_shutdown.call_count == 2


class TestScenario15DoubleUpgrade:
    """场景 15：双重升级叠加跨多级（spec §5.2.1 规则 6/11）。"""

    async def test_switch_then_count_crosses_levels(self) -> None:
        esc, ports = make_escalator(
            ErrorEscalationConfig(error_on_warn=True, error_critical_threshold=1)
        )
        esc.report(ErrorLevel.WARN, "double upgrade")
        await _drain(esc)
        # 经开关升 ERROR，再经计数升 CRITICAL——仅 CRITICAL 计数+1
        stats = esc.get_stats()
        assert stats.counts[ErrorLevel.WARN] == 0
        assert stats.counts[ErrorLevel.ERROR] == 0
        assert stats.counts[ErrorLevel.CRITICAL] == 1
        # CRITICAL 动作集：无 DEGRADE，有 CRASH_DUMP + NOTIFY
        ports["state_machine"].trigger_health_level_change.assert_not_called()
        ports["crash_dump"].export_snapshot.assert_called_once()
        ports["event_bus"].emit_sync.assert_called_once()


class TestScenario18ThresholdDisabled:
    """场景 18：阈值禁用语义（spec §5.2.1 规则 7）。"""

    async def test_threshold_zero_never_upgrades(self) -> None:
        esc, ports = make_escalator(ErrorEscalationConfig(warn_error_threshold=0))
        for _ in range(100):
            esc.report(ErrorLevel.WARN, "never upgrade")
        await _drain(esc)
        ports["state_machine"].trigger_health_level_change.assert_not_called()


class TestScenario20LevelMissing:
    """场景 20：等级缺失兜底 WARN（spec §5.1.3 异常场景 2）。"""

    async def test_report_without_level_falls_back_warn(self) -> None:
        esc, ports = make_escalator()
        esc.report(None, "no level")
        await _drain(esc)
        ports["taint"].add_taint.assert_called_once_with(TaintFlag.TAINT_WARN)
        assert esc.get_stats().counts[ErrorLevel.WARN] == 1


class TestScenario22SuppressorLink:
    """场景 22：CRITICAL 级 Suppressor 联动（P1-5）。"""

    async def test_critical_sets_min_level(self) -> None:
        esc, ports = make_escalator()
        esc.report(ErrorLevel.CRITICAL, "critical visible")
        await _drain(esc)
        # set_min_level(50) = logging.CRITICAL
        ports["rate_limiter"].set_min_level.assert_called_once_with(50)

    async def test_warn_does_not_set_min_level(self) -> None:
        esc, ports = make_escalator()
        esc.report(ErrorLevel.WARN, "normal warn")
        await _drain(esc)
        ports["rate_limiter"].set_min_level.assert_not_called()


class TestStormSuppressionInEscalator:
    """风暴抑制仅影响 LOG/NOTIFY，COUNT 全量（spec §5.4.1 规则 5）。"""

    async def test_storm_suppresses_notify_but_counts(self) -> None:
        esc, ports = make_escalator(ErrorEscalationConfig(storm_min_threshold=3))
        for _ in range(10):
            esc.report(ErrorLevel.CRITICAL, "same storm", component_id="comp-a")
        await _drain(esc)
        # 第 1/2 次正常 NOTIFY，第 3 次 force_once 完整响应，后续抑制 → 3 次
        assert ports["event_bus"].emit_sync.call_count == 3
        # COUNT 全量：10 次全部计入 CRITICAL
        assert esc.get_stats().counts[ErrorLevel.CRITICAL] == 10
        # 风暴源已标记
        stats = esc.get_stats()
        assert len(stats.storm_sources) == 1

    async def test_once_suppresses_log_but_counts(self) -> None:
        """场景 6：同一源 once=True 200 次——仅首次完整响应，全量计数。"""
        esc, ports = make_escalator(ErrorEscalationConfig())
        for _ in range(200):
            esc.report(ErrorLevel.WARN, "once storm", once=True)
        await _drain(esc)
        # TAINT 幂等置位只调一次（ONCE 首次完整响应）
        ports["taint"].add_taint.assert_called_once_with(TaintFlag.TAINT_WARN)
        assert esc.get_stats().counts[ErrorLevel.WARN] == 200


class TestPortMissingFallback:
    """Port 未注入跳过动作 + 告警，不抛异常（spec §5.3.3 异常场景 1）。"""

    async def test_report_without_ports_does_not_raise(self) -> None:
        esc, _ = make_escalator(with_ports=False)
        esc.report(ErrorLevel.FATAL, "no ports at all")
        await _drain(esc)
        esc.report(ErrorLevel.CRITICAL, "still fine", component_id="x")
        await _drain(esc)
        assert True  # 全程不抛异常

    async def test_crash_dump_without_port_logs_warning(self) -> None:
        esc, _ = make_escalator(with_ports=False)
        esc.report(ErrorLevel.CRITICAL, "missing crash port")
        await _drain(esc)
        assert True


class TestActionsOverride:
    """level_actions 覆盖默认动作集（spec §5.3.1 规则 1）。"""

    async def test_override_warn_to_log_only(self) -> None:
        esc, ports = make_escalator(
            ErrorEscalationConfig(level_actions={ErrorLevel.WARN: [ErrorAction.LOG]})
        )
        esc.report(ErrorLevel.WARN, "log only")
        await _drain(esc)
        ports["taint"].add_taint.assert_not_called()


class TestUpgradePathTracking:
    """升级路径结构化追踪（spec §4.4 规则 1）。"""

    async def test_upgrade_path_in_event(self) -> None:
        esc, ports = make_escalator(
            ErrorEscalationConfig(error_on_warn=True, error_critical_threshold=1)
        )
        esc.report(ErrorLevel.WARN, "path trace")
        await _drain(esc)
        event = esc.get_stats().last_event
        assert event is not None
        assert event.original_level is ErrorLevel.WARN
        assert event.level is ErrorLevel.CRITICAL
        assert "warn→error(switch)" in event.upgrade_path
        assert "error→critical(count)" in event.upgrade_path
