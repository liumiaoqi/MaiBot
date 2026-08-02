"""ZG-7 T23 端到端验证 — 完整生命周期 + 配置加载 + 接线完整性。"""

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


class TestEndToEndLifecycle:
    @pytest.mark.asyncio
    async def test_full_lifecycle(self) -> None:
        """完整生命周期：位图从 0 开始 → 多位置位 → 不可逆 → 幂等 → 动作 → 通知 → 内省 → 导出。"""
        sm = _FakeStateMachine()
        adapter = TaintMaskAdapter(
            state_machine_port=sm,
            app_config_port=type(
                "Cfg",
                (),
                {
                    "get_taint_on_taint": lambda self: {"TAINT_PORT_BYPASS": "trigger_degrade"},
                    "get_taint_warn_limit": lambda self: 0,
                    "get_taint_preset_mask": lambda self: 0,
                },
            )(),
        )
        events: list[object] = []
        adapter.subscribe(lambda e: events.append(e))

        # 1. 位图从 0 开始
        assert adapter.get_taint() == 0
        assert adapter.print_tainted() == "Not tainted"

        # 2. 多位置位
        adapter.add_taint(TaintFlag.TAINT_PORT_BYPASS)
        adapter.add_taint(TaintFlag.TAINT_WARN)
        assert adapter.get_taint() == 0x21
        assert adapter.print_tainted() == "Tainted: P    W  "

        # 3. 不可逆 + 幂等
        adapter.add_taint(TaintFlag.TAINT_PORT_BYPASS)
        adapter.add_taint(TaintFlag.TAINT_WARN)
        assert adapter.get_taint() == 0x21
        assert len(events) == 2  # 幂等不重复广播

        # 4. 动作触发（TRIGGER_DEGRADE 驱动降级）
        for _ in range(50):
            if sm.calls:
                break
            await asyncio.sleep(0.01)
        assert sm.calls == ["fault"]

        # 5. 内省输出
        assert adapter.print_tainted_verbose() == [
            "P=TAINT_PORT_BYPASS",
            "W=TAINT_WARN",
        ]
        assert len(adapter.get_taint_records()) == 2
        assert adapter.warn_count == 2  # 含幂等分支递增（计数非动作）

        # 6. 导出含污染行
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
        dump = CrashDump(ring_buffer=buffer, log_dir=tmp, enabled=True)
        dump.set_taint_mask_port(adapter)
        dump.export("e2e")
        files = list(tmp.glob("dump_*.log.jsonl"))
        assert len(files) == 1
        first = json.loads(files[0].read_text(encoding="utf-8").strip().split("\n")[0])
        assert first["tainted_mask"] == 0x21
        assert "W=TAINT_WARN" in first["tainted_verbose"]


class TestConfigEndToEnd:
    def test_config_chain(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """配置加载端到端：配置节 → AppConfigPort → TaintMaskAdapter → on_taint 映射生效。"""
        from src.config.config import Config
        from src.core.adapters.app_config_port import GlobalConfigAppConfigPort

        class _FakeManager:
            def get_global_config(self) -> Config:
                return Config()

            def get_model_config(self) -> Config:
                return Config()

        monkeypatch.setattr("src.config.config.config_manager", _FakeManager())

        # 真实 AppConfigPort（从 bot_config.toml 读 [tainted_mask] 节）
        app_port = GlobalConfigAppConfigPort()
        on_taint = app_port.get_taint_on_taint()
        warn_limit = app_port.get_taint_warn_limit()
        preset_mask = app_port.get_taint_preset_mask()
        # 默认值（配置节默认空/0）
        assert on_taint == {}
        assert warn_limit == 0
        assert preset_mask == 0

        # 经适配器构建（无 state_machine → TRIGGER_DEGRADE 降级 WARN 不抛错）
        adapter = TaintMaskAdapter(app_config_port=app_port)
        assert adapter.get_taint() == 0
        assert adapter.warn_count == 0
        adapter.add_taint(TaintFlag.TAINT_WARN)
        assert adapter.get_taint() == 0x20


class TestWiringCompleteness:
    def test_adapter_instantiation_point(self) -> None:
        """TaintMaskAdapter 有明确实例化点（无零接线，spec §5.5 规则 2）。"""
        import src.main as main_module

        source = Path(main_module.__file__).read_text(encoding="utf-8")
        assert "_init_tainted_mask" in source, "main.py 缺少 _init_tainted_mask 实例化点"
        assert "TaintMaskAdapter(" in source, "main.py 缺少 TaintMaskAdapter 实例化"

    def test_registry_wiring(self) -> None:
        """registry 注册/查询可用。"""
        from src.core.protocols import TaintedMaskPort
        from src.core.taint_mask_port_registry import (
            get_taint_mask_port,
            reset_taint_mask_port,
            set_taint_mask_port,
        )

        reset_taint_mask_port()
        adapter = TaintMaskAdapter(app_config_port=None)
        set_taint_mask_port(adapter)
        assert isinstance(get_taint_mask_port(), TaintedMaskPort)
        reset_taint_mask_port()

    def test_structured_log_fields(self) -> None:
        """add_taint 结构化日志字段完整（spec §4.2 规则 1）。"""
        import logging

        records: list[logging.LogRecord] = []

        class _Handler(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                records.append(record)

        from src.core.tainted_mask import tainted_mask as tm_module

        handler = _Handler()
        tm_module.logger.addHandler(handler)
        try:
            adapter = TaintMaskAdapter(app_config_port=None)
            adapter.add_taint(TaintFlag.TAINT_WARN)
        finally:
            tm_module.logger.removeHandler(handler)

        assert records, "add_taint 未输出日志"
        record = records[0]
        assert "污染位置位" in record.getMessage()
        assert "TAINT_WARN" in record.getMessage()
        assert "0x20" in record.getMessage()
