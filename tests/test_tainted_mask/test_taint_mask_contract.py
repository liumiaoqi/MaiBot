"""ZG-7 T13 契约测试 — TaintedMaskPort Protocol 契约 + 适配器委托。"""


from src.core.adapters.taint_mask_adapter import TaintMaskAdapter
from src.core.protocols import TaintedMaskPort
from src.core.tainted_mask.taint_flag import TaintFlag


class _FakeConfigPort:
    def get_taint_on_taint(self) -> dict[str, str]:
        return {"TAINT_PORT_BYPASS": "trigger_degrade"}

    def get_taint_warn_limit(self) -> int:
        return 5

    def get_taint_preset_mask(self) -> int:
        return 0

    def get_degrade_on_taint_mask(self) -> int:
        return 0


def _make_adapter() -> TaintMaskAdapter:
    return TaintMaskAdapter(app_config_port=_FakeConfigPort())


class TestContract:
    def test_port_protocol_conformance(self) -> None:
        """isinstance(adapter, TaintedMaskPort) 为 True（spec §4.6 规则 3）。"""
        assert isinstance(_make_adapter(), TaintedMaskPort)

    def test_all_methods_present(self) -> None:
        adapter = _make_adapter()
        for method in (
            "add_taint",
            "test_taint",
            "get_taint",
            "print_tainted",
            "print_tainted_verbose",
            "get_taint_records",
            "warn_count",
            "get_degrade_on_taint_mask",
        ):
            assert hasattr(adapter, method), f"缺失方法: {method}"


class TestAdapterDelegation:
    def test_add_taint_delegates(self) -> None:
        adapter = _make_adapter()
        adapter.add_taint(TaintFlag.TAINT_WARN)
        assert adapter.get_taint() == 0x20

    def test_get_taint_delegates(self) -> None:
        adapter = _make_adapter()
        assert adapter.get_taint() == 0

    def test_print_tainted_delegates(self) -> None:
        adapter = _make_adapter()
        adapter.add_taint(TaintFlag.TAINT_WARN)
        assert adapter.print_tainted() == "Tainted: G    W  "

    def test_warn_count_delegates(self) -> None:
        adapter = _make_adapter()
        adapter.add_taint(TaintFlag.TAINT_WARN)
        assert adapter.warn_count == 1

    def test_get_taint_records_delegates(self) -> None:
        adapter = _make_adapter()
        adapter.add_taint(TaintFlag.TAINT_WARN)
        assert len(adapter.get_taint_records()) == 1


class TestAdapterConfigLoading:
    def test_config_loading(self) -> None:
        """配置加载 on_taint / warn_limit / preset_mask 正确。"""
        adapter = _make_adapter()
        # on_taint: TAINT_PORT_BYPASS → TRIGGER_DEGRADE
        assert adapter._tainted_mask._on_taint.get(TaintFlag.TAINT_PORT_BYPASS).value == "trigger_degrade"
        # warn_limit
        assert adapter._tainted_mask._warn_limit == 5
        # preset_mask
        assert adapter._tainted_mask._mask == 0

    def test_no_config_defaults(self) -> None:
        """无配置端口时默认值。"""
        adapter = TaintMaskAdapter(app_config_port=None)
        assert adapter.get_taint() == 0
        assert adapter.warn_count == 0

    def test_subscribe_delegates(self) -> None:
        adapter = _make_adapter()
        events: list[object] = []
        handle = adapter.subscribe(lambda e: events.append(e))
        adapter.add_taint(TaintFlag.TAINT_WARN)
        assert len(events) == 1
        adapter.unsubscribe(handle)

    def test_get_degrade_on_taint_mask_delegates(self) -> None:
        adapter = _make_adapter()
        assert adapter.get_degrade_on_taint_mask() == adapter._tainted_mask.get_degrade_on_taint_mask()
