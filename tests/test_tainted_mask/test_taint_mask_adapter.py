"""ZG-7 T18 集成测试 — 状态机降级 / 视图扩展 / crash_dump / warn 端到端。"""

import asyncio
import json
import tempfile
from pathlib import Path

import pytest

from src.core.adapters.taint_mask_adapter import TaintMaskAdapter
from src.core.tainted_mask.taint_flag import TaintFlag


class _FakeStateMachine:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def trigger_health_level_change(self, level: str) -> None:
        self.calls.append(level)


class _FakeConfigPort:
    def get_taint_on_taint(self) -> dict[str, str]:
        return {"TAINT_PORT_BYPASS": "trigger_degrade"}

    def get_taint_warn_limit(self) -> int:
        return 3

    def get_taint_preset_mask(self) -> int:
        return 0

    def get_degrade_on_taint_mask(self) -> int:
        return 0


class TestStateMachineIntegration:
    @pytest.mark.asyncio
    async def test_trigger_degrade_drives_readytodegrading(self) -> None:
        """TRIGGER_DEGRADE 驱动 READY→DEGRADING（spec §2.3.1 规则 4）。"""
        sm = _FakeStateMachine()
        adapter = TaintMaskAdapter(
            state_machine_port=sm, app_config_port=_FakeConfigPort()
        )
        adapter.add_taint(TaintFlag.TAINT_PORT_BYPASS)
        for _ in range(50):
            if sm.calls:
                break
            await asyncio.sleep(0.01)
        assert sm.calls == ["fault"]


class TestSystemLifecycleView:
    def test_view_tainted_mask_field(self) -> None:
        """SystemLifecycleView 含 tainted_mask 字段（spec §2.4.1 规则 4）。"""
        from src.core.system_state.state_machine import SystemStateMachine

        sm = SystemStateMachine(history_capacity=10, notify_timeout=1.0)
        view = sm.get_view(
            health_level="healthy",
            core_readiness=(True, True, True),
            tainted_mask=0x20,
            tainted_verbose=["W=TAINT_WARN"],
        )
        assert view.tainted_mask == 0x20
        assert view.tainted_verbose == ["W=TAINT_WARN"]

    def test_view_defaults(self) -> None:
        """默认值 0 / 空列表（向前兼容）。"""
        from src.core.system_state.state_machine import SystemStateMachine

        sm = SystemStateMachine(history_capacity=10, notify_timeout=1.0)
        view = sm.get_view(health_level="healthy", core_readiness=(True, True, True))
        assert view.tainted_mask == 0
        assert view.tainted_verbose == []


class TestCrashDumpTaintedLine:
    def _make_dump(self) -> tuple[object, Path, object]:
        """构造带污染的 CrashDump + 注入 port。"""
        from src.common.log_pipeline.crash_dump import CrashDump
        from src.common.log_pipeline.ring_buffer import RingBuffer

        buffer = RingBuffer(capacity=10, max_bytes=65536, entry_max_bytes=4096)
        # 写一条日志进缓冲
        buffer.append(
            type(
                "Entry",
                (),
                {
                    "sequence": 1,
                    "timestamp": "2026-08-02 10:00:00",
                    "level": "INFO",
                    "logger_name": "test",
                    "module": "test",
                    "event": "hello",
                    "rate_limit": False,
                    "truncated": False,
                    "extra": {},
                },
            )()
        )
        tmp = Path(tempfile.mkdtemp())
        dump = CrashDump(ring_buffer=buffer, log_dir=Path(tmp), enabled=True)
        adapter = TaintMaskAdapter(app_config_port=_FakeConfigPort())
        adapter.add_taint(TaintFlag.TAINT_WARN)
        dump.set_taint_mask_port(adapter)
        return dump, Path(tmp), buffer

    def test_crash_dump_tainted_line(self) -> None:
        """CrashDump 导出含污染状态首行（spec §4.5 规则 1）。"""
        dump, tmp, _ = self._make_dump()
        dump.export("test")
        files = list(tmp.glob("dump_*.log.jsonl"))
        assert len(files) == 1
        lines = files[0].read_text(encoding="utf-8").strip().split("\n")
        first = json.loads(lines[0])
        assert "tainted_mask" in first
        assert first["tainted_mask"] == 0x20
        assert first["tainted_verbose"] == ["W=TAINT_WARN"]

    def test_no_port_skips_taint_line(self) -> None:
        """port 未注入时跳过污染行（渐进启用，spec §5.5 规则 2）。"""
        from src.common.log_pipeline.crash_dump import CrashDump
        from src.common.log_pipeline.ring_buffer import RingBuffer

        buffer = RingBuffer(capacity=10, max_bytes=65536, entry_max_bytes=4096)
        buffer.append(
            type(
                "Entry",
                (),
                {
                    "sequence": 1,
                    "timestamp": "2026-08-02 10:00:00",
                    "level": "INFO",
                    "logger_name": "test",
                    "module": "test",
                    "event": "hello",
                    "rate_limit": False,
                    "truncated": False,
                    "extra": {},
                },
            )()
        )
        tmp = Path(tempfile.mkdtemp())
        dump = CrashDump(ring_buffer=buffer, log_dir=Path(tmp), enabled=True)
        dump.export("test")
        files = list(tmp.glob("dump_*.log.jsonl"))
        lines = files[0].read_text(encoding="utf-8").strip().split("\n")
        assert "tainted_mask" not in json.loads(lines[0])


class TestWarnEndToEnd:
    @pytest.mark.asyncio
    async def test_warn_count_and_limit_integration(self) -> None:
        """warn_count 递增 + warn_limit 触发降级端到端。"""
        sm = _FakeStateMachine()
        adapter = TaintMaskAdapter(state_machine_port=sm, app_config_port=_FakeConfigPort())
        adapter.add_taint(TaintFlag.TAINT_WARN)
        adapter.add_taint(TaintFlag.TAINT_WARN)
        assert adapter.warn_count == 2
        assert sm.calls == []
        adapter.add_taint(TaintFlag.TAINT_WARN)  # 达 warn_limit=3
        for _ in range(50):
            if sm.calls:
                break
            await asyncio.sleep(0.01)
        assert sm.calls == ["fault"]


class TestDegradeOnTaintMaskAdapter:
    def test_adapter_loads_degrade_on_taint_mask(self) -> None:
        """适配器正常加载 degrade_on_taint_mask 配置。"""

        class _ConfigWithMask(_FakeConfigPort):
            def get_degrade_on_taint_mask(self) -> int:
                return 0x03

        adapter = TaintMaskAdapter(app_config_port=_ConfigWithMask())
        assert adapter.get_degrade_on_taint_mask() == 0x03

    def test_adapter_no_config_port_defaults_zero(self) -> None:
        """app_config_port=None 时使用默认值 0。"""
        adapter = TaintMaskAdapter(app_config_port=None)
        assert adapter.get_degrade_on_taint_mask() == 0

    def test_adapter_config_read_exception_defaults_zero(self) -> None:
        """配置读取异常时使用默认值 0。"""

        class _BrokenConfig(_FakeConfigPort):
            def get_degrade_on_taint_mask(self) -> int:
                raise RuntimeError("配置读取失败")

        adapter = TaintMaskAdapter(app_config_port=_BrokenConfig())
        assert adapter.get_degrade_on_taint_mask() == 0

    def test_adapter_invalid_range_raises(self) -> None:
        """超范围值由 TaintedMask 构造时抛 ValueError。"""

        class _BadConfig(_FakeConfigPort):
            def get_degrade_on_taint_mask(self) -> int:
                return 0x100

        with pytest.raises(ValueError, match="degrade_on_taint_mask 超范围"):
            TaintMaskAdapter(app_config_port=_BadConfig())

    def test_adapter_degrade_on_taint_mask_delegates(self) -> None:
        """get_degrade_on_taint_mask 委托正确。"""

        class _ConfigWithMask(_FakeConfigPort):
            def get_degrade_on_taint_mask(self) -> int:
                return 0x05

        adapter = TaintMaskAdapter(app_config_port=_ConfigWithMask())
        assert adapter.get_degrade_on_taint_mask() == adapter._tainted_mask.get_degrade_on_taint_mask()
