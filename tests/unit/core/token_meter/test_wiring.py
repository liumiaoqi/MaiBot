"""ZG-N6 TokenMeter 接线测试——覆盖接线完整性四连问。

不只 grep 字符串——实际调用 _init_token_meter() 构造链，
断言 get_token_meter() is not None + is 判断同一实例。
"""

import pytest

import src.core.token_meter.service as svc
from src.core.token_meter import TokenMeter, get_token_meter


class TestStartupItemRegistered:
    def test_init_fn_exists_in_main(self):
        from src.main import MainSystem
        assert hasattr(MainSystem, "_init_token_meter")

    def test_startup_item_decorator_applied(self):
        from src.core.startup.declaration import _registry
        names = list(_registry._items.keys())
        assert "token_meter" in names


class TestInitFnCreatesSingleton:
    @pytest.fixture(autouse=True)
    def cleanup(self):
        original = svc._instance
        yield
        svc._instance = original

    @pytest.mark.asyncio
    async def test_init_creates_instance(self):
        from src.main import MainSystem
        await MainSystem._init_token_meter()
        assert get_token_meter() is not None

    @pytest.mark.asyncio
    async def test_init_idempotent(self):
        from src.main import MainSystem
        await MainSystem._init_token_meter()
        m1 = get_token_meter()
        await MainSystem._init_token_meter()
        m2 = get_token_meter()
        assert m1 is not None
        assert m2 is not None

    @pytest.mark.asyncio
    async def test_get_before_init_raises(self):
        svc._instance = None
        with pytest.raises(RuntimeError, match="未接线"):
            get_token_meter()


class TestN5Adapter:
    def test_adapter_implements_n5_port(self):
        from src.core.token_meter import N5TokenMeterAdapter
        from src.A_memorix.core.runtime.services.compaction.ports import TokenMeterPort

        meter = TokenMeter()
        adapter = N5TokenMeterAdapter(meter)
        assert isinstance(adapter, TokenMeterPort)

    def test_count_tokens_delegates(self):
        from src.core.token_meter import N5TokenMeterAdapter

        meter = TokenMeter()
        adapter = N5TokenMeterAdapter(meter)
        assert adapter.count_tokens("abcd") == meter.estimate_text("abcd")

    def test_count_events_tokens_delegates(self):
        from src.core.token_meter import N5TokenMeterAdapter

        meter = TokenMeter()
        adapter = N5TokenMeterAdapter(meter)
        events = [
            {"role": "user", "content": "abcd"},
            {"role": "assistant", "content": "efgh"},
        ]
        expected = sum(meter.estimate(e) for e in events)
        assert adapter.count_events_tokens(events) == expected

    def test_get_context_window_delegates(self):
        from src.core.token_meter import N5TokenMeterAdapter

        meter = TokenMeter()
        adapter = N5TokenMeterAdapter(meter)
        assert adapter.get_context_window(None) == meter.get_context_window(None)