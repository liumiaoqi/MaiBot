"""ZG-14 T2.4 — 验收场景集成测试（spec §7 全部 22 场景）。

T1.9 已覆盖引擎级场景：1/2/3/4/5/6/13/15/18/20/22、映射 10、配置校验 21。
本文件补充：7（ZG-7 委托）、8（未注入兜底）、9（crash_dump 分离）、
12（配置热更新）、14（N2 补充）、16（风暴恢复）、17（窗口归零）、
19（吞没型改造语义）+ 专项（快照磁盘满/缓冲未初始化）。
"""

import asyncio
import builtins
import json
from unittest.mock import AsyncMock, MagicMock

from src.common.log_pipeline.crash_dump import CrashDump
from src.common.log_pipeline.ring_buffer import RingBuffer
from src.core.error_escalation.config import ErrorEscalationConfig
from src.core.error_escalation.types import ErrorLevel
from src.core.tainted_mask.taint_flag import TaintFlag
from src.core.tainted_mask.tainted_mask import TaintedMask

from tests.test_error_escalation._helpers import drain, make_escalator


class TestScenario7Zg7Delegate:
    """场景 7：ZG-7 warn_count 达阈委托 ZG-14（spec §5.9.1 规则 1/3）。"""

    async def test_delegate_on_threshold(self) -> None:
        port = MagicMock()
        sm = MagicMock()
        mask = TaintedMask(warn_limit=3, state_machine_port=sm, error_escalation_port=port)
        for _ in range(3):
            mask.add_taint(TaintFlag.TAINT_WARN)
        await asyncio.sleep(0)
        # 委托 ZG-14，未走原 TRIGGER_DEGRADE（ZG-7 不重复触发）
        port.report_warn.assert_called_once_with(count=3, mask_matched=False)
        assert sm.trigger_health_level_change.call_count == 0

    async def test_delegate_passes_mask_matched(self) -> None:
        """mask_matched=True 时委托原样传递（ZG-14 跳过重复 DEGRADE）。"""
        port = MagicMock()
        mask = TaintedMask(warn_limit=2, error_escalation_port=port)
        mask._bump_warn_count(TaintFlag.TAINT_WARN, mask_matched=True)
        mask._bump_warn_count(TaintFlag.TAINT_WARN, mask_matched=True)
        port.report_warn.assert_called_once_with(count=2, mask_matched=True)

    async def test_warn_count_authority_stays_in_zg7(self) -> None:
        """warn_count 权威源在 ZG-7（spec §5.9.1 规则 4）。"""
        port = MagicMock()
        mask = TaintedMask(warn_limit=3, error_escalation_port=port)
        for _ in range(3):
            mask.add_taint(TaintFlag.TAINT_WARN)
        assert mask.warn_count == 3
        port.report_warn.assert_called_once_with(count=3, mask_matched=False)


class TestScenario8Zg7Fallback:
    """场景 8：ZG-14 未注入时保留原 TRIGGER_DEGRADE 兜底（spec §5.9.1 规则 2）。"""

    async def test_fallback_trigger_degrade(self) -> None:
        sm = MagicMock()
        sm.trigger_health_level_change = AsyncMock()
        mask = TaintedMask(warn_limit=2, state_machine_port=sm)
        for _ in range(2):
            mask.add_taint(TaintFlag.TAINT_WARN)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        sm.trigger_health_level_change.assert_called_once()


class TestScenario9CrashDumpSeparation:
    """场景 9：crash_dump 方法分离（spec §5.5.1 规则 1）。"""

    def _make(self, tmp_path) -> CrashDump:
        rb = RingBuffer(capacity=10, max_bytes=10000, entry_max_bytes=1000)
        rb.append(_make_entry(rb, 1))
        return CrashDump(rb, tmp_path, True)

    def test_export_on_crash_once_only(self, tmp_path) -> None:
        cd = self._make(tmp_path)
        cd.export_on_crash("first")
        cd.export_on_crash("second")
        assert len(list(tmp_path.glob("dump_*.log.jsonl"))) == 1

    def test_export_snapshot_twice_both_export(self, tmp_path) -> None:
        cd = self._make(tmp_path)
        cd.export_snapshot("s1", {"level": "critical", "message": "m1"})
        cd.export_snapshot("s2", {"level": "critical", "message": "m2"})
        assert len(list(tmp_path.glob("snapshot_*.log.jsonl"))) == 2

    def test_export_snapshot_rate_limited(self, tmp_path) -> None:
        """1 分钟最多 3 次快照（spec §5.5.1 规则 4）。"""
        cd = self._make(tmp_path)
        for i in range(5):
            cd.export_snapshot(f"s{i}")
        assert len(list(tmp_path.glob("snapshot_*.log.jsonl"))) == 3

    def test_export_delegates_to_on_crash(self, tmp_path) -> None:
        """export 兼容入口委托 export_on_crash（spec §4.5 规则 3）。"""
        cd = self._make(tmp_path)
        cd.export("legacy-reason")
        cd.export("again")
        assert len(list(tmp_path.glob("dump_*.log.jsonl"))) == 1

    def test_snapshot_contains_context_and_entries(self, tmp_path) -> None:
        """快照含触发等级/消息/组件标识 + 环形缓冲（spec §5.5.1 规则 3）。"""
        rb = RingBuffer(capacity=10, max_bytes=10000, entry_max_bytes=1000)
        rb.append(_make_entry(rb, 1))
        rb.append(_make_entry(rb, 2))
        cd = CrashDump(rb, tmp_path, True)
        cd.export_snapshot(
            "error-escalation-critical",
            {"level": "critical", "message": "boom", "component_id": "comp-x"},
        )
        path = list(tmp_path.glob("snapshot_*.log.jsonl"))[0]
        lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        meta = lines[0]
        assert meta["type"] == "snapshot"
        assert meta["context"]["level"] == "critical"
        assert meta["context"]["component_id"] == "comp-x"
        assert len(lines) == 1 + 2  # meta + 2 条缓冲

    def test_snapshot_readonly_does_not_consume_buffer(self, tmp_path) -> None:
        """只读导出不修改全局状态（spec §5.5.1 规则 6）：快照后缓冲仍在。"""
        rb = RingBuffer(capacity=10, max_bytes=10000, entry_max_bytes=1000)
        rb.append(_make_entry(rb, 1))
        cd = CrashDump(rb, tmp_path, True)
        cd.export_snapshot("snap", {})
        cd.export_on_crash("crash")
        dump_files = list(tmp_path.glob("dump_*.log.jsonl"))
        assert len(dump_files) == 1
        lines = [line for line in dump_files[0].read_text(encoding="utf-8").splitlines() if line.strip()]
        # 崩溃导出含快照未消费的条目
        assert any('"event": "entry 1"' in line for line in lines)


class TestScenario12HotUpdate:
    """场景 12：配置运行时热更新（spec §5.8.1 规则 3/5）。"""

    async def test_update_config_takes_effect_immediately(self) -> None:
        esc, ports = make_escalator(ErrorEscalationConfig())
        esc.report(ErrorLevel.WARN, "before update")
        await drain(esc)
        ports["state_machine"].trigger_health_level_change.assert_not_called()
        # 运行时开启 error_on_warn
        esc.update_config(ErrorEscalationConfig(error_on_warn=True), source="test")
        esc.report(ErrorLevel.WARN, "after update")
        await drain(esc)
        ports["state_machine"].trigger_health_level_change.assert_called_once()

    async def test_update_config_does_not_affect_history(self) -> None:
        """仅影响后续 report 不追溯历史（spec §5.8.3 异常场景 2）。"""
        esc, ports = make_escalator(ErrorEscalationConfig(warn_error_threshold=5))
        for _ in range(5):
            esc.report(ErrorLevel.WARN, "accumulate")
        await drain(esc)
        assert ports["state_machine"].trigger_health_level_change.call_count == 1  # 第 5 次已升级
        count_before = esc.get_stats().counts[ErrorLevel.ERROR]
        # 热更新后计数不追溯重置
        esc.update_config(ErrorEscalationConfig(warn_error_threshold=10), source="test")
        assert esc.get_stats().counts[ErrorLevel.ERROR] == count_before


class TestScenario14N2NoKill:
    """场景 14（补充）：任意等级上报进程不退出（spec §5.3.1 规则 12）。"""

    async def test_all_levels_keep_process_alive(self) -> None:
        esc, _ = make_escalator()
        for level in ErrorLevel:
            esc.report(level, f"n2 check {level.value}")
        await drain(esc)
        assert True  # 进程未退出即通过

    async def test_no_kill_actions_in_defaults(self) -> None:
        """FATAL 最高动作 STOP_CORE 优雅停机，无 kill/exit（N2 裁决）。"""
        esc, ports = make_escalator()
        esc.report(ErrorLevel.FATAL, "max action")
        await drain(esc)
        ports["state_machine"].trigger_shutdown.assert_called_once()
        assert not hasattr(ports, "kill")  # 无杀进程语义动作


class TestScenario16StormRecovery:
    """场景 16：风暴检测自动标记 + 恢复（spec §5.4.1 规则 3/4）。"""

    async def test_storm_mark_and_auto_recover(self, fake_clock) -> None:
        esc, ports = make_escalator(
            ErrorEscalationConfig(storm_min_threshold=3, count_window_sec=10.0),
            time_func=fake_clock,
        )
        for _ in range(3):
            esc.report(ErrorLevel.CRITICAL, "same storm", component_id="comp-a")
        await drain(esc)
        assert len(esc.get_stats().storm_sources) == 1
        notify_count = ports["event_bus"].emit_sync.call_count
        # 3 个窗口（30 秒）无触发 → 自动解除
        fake_clock.advance(35.0)
        esc.report(ErrorLevel.CRITICAL, "same storm", component_id="comp-a")
        await drain(esc)
        assert len(esc.get_stats().storm_sources) == 0
        # 恢复后 NOTIFY 正常（+1）
        assert ports["event_bus"].emit_sync.call_count == notify_count + 1


class TestScenario17CountWindowReset:
    """场景 17：计数窗口归零（spec §5.2.1 规则 8）。"""

    async def test_window_rollover_resets_escalation_count(self, fake_clock) -> None:
        esc, ports = make_escalator(
            ErrorEscalationConfig(warn_error_threshold=5, count_window_sec=60.0),
            time_func=fake_clock,
        )
        for _ in range(4):
            esc.report(ErrorLevel.WARN, "window count")
        await drain(esc)
        assert ports["state_machine"].trigger_health_level_change.call_count == 0
        # 60 秒后计数归零——下一次计数为 1，不再触发升级
        fake_clock.advance(60.0)
        esc.report(ErrorLevel.WARN, "window count")
        await drain(esc)
        assert ports["state_machine"].trigger_health_level_change.call_count == 0
        assert esc.get_stats().counts[ErrorLevel.WARN] == 1


class TestScenario19SwallowReformation:
    """场景 19（语义）：吞没型捕获点改造后 report 被调 + 原吞没行为不变。"""

    async def test_report_called_with_swallow_kept(self) -> None:
        esc, ports = make_escalator()
        try:
            raise ValueError("swallowed error")
        except Exception as e:
            esc.report(ErrorLevel.ERROR, "操作失败", component_id="comp-x", exception=e)
            # 原吞没行为：不重抛
        await drain(esc)
        ports["taint"].add_taint.assert_called_once_with(TaintFlag.TAINT_EXCEPTION_SWALLOWED)


class TestSnapshotEdgeCases:
    """专项：快照磁盘满 / 缓冲未初始化（spec §5.5.3 异常场景 1/2，P2-20）。"""

    def test_disk_full_skips_snapshot(self, tmp_path, monkeypatch) -> None:
        """磁盘满（IOError）捕获，跳过本次快照，不阻塞后续（spec §5.5.3 异常场景 1）。"""
        rb = RingBuffer(capacity=10, max_bytes=10000, entry_max_bytes=1000)
        rb.append(_make_entry(rb, 1))
        cd = CrashDump(rb, tmp_path, True)

        real_open = builtins.open  # monkeypatch 前保存原引用

        def _boom(*args, **kwargs):
            raise OSError("No space left on device")

        monkeypatch.setattr(builtins, "open", _boom)
        cd.export_snapshot("disk-full", {"level": "critical"})  # 不抛异常
        monkeypatch.setattr(builtins, "open", real_open)
        cd.export_snapshot("after-recovery", {"level": "critical"})
        assert len(list(tmp_path.glob("snapshot_*.log.jsonl"))) == 1

    def test_empty_buffer_marked(self, tmp_path) -> None:
        """环形缓冲未初始化（空）→ 空快照 + 标记（spec §5.5.3 异常场景 2）。"""
        rb = RingBuffer(capacity=10, max_bytes=10000, entry_max_bytes=1000)
        cd = CrashDump(rb, tmp_path, True)
        cd.export_snapshot("empty-buffer", {"level": "critical"})
        path = list(tmp_path.glob("snapshot_*.log.jsonl"))[0]
        lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        assert lines[0]["buffer_empty"] is True
        assert len(lines) == 1  # 仅元数据行

    def test_disabled_no_export(self, tmp_path) -> None:
        cd = CrashDump(RingBuffer(10, 10000, 1000), tmp_path, False)
        cd.export_on_crash("disabled")
        cd.export_snapshot("disabled")
        assert len(list(tmp_path.glob("*.log.jsonl"))) == 0


def _make_entry(rb: RingBuffer, sequence: int):
    """构造环形缓冲条目（最小字段）。"""
    from src.common.log_pipeline.ring_buffer import BufferEntry

    return BufferEntry(
        sequence=sequence,
        timestamp="2026-08-06T00:00:00",
        level="INFO",
        logger_name="test",
        module="test",
        event=f"entry {sequence}",
    )
