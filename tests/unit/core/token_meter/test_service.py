"""ZG-N6 TokenMeter 单例服务测试。"""

import pytest

from src.core.token_meter.service import (
    DEFAULT_CONTEXT_WINDOW,
    TokenMeter,
    _set_instance,
    get_token_meter,
)
from src.core.token_meter.types import (
    TokenMeasurement,
    TokenMeasurementBaseline,
    TokenSurfaceNode,
)


@pytest.fixture
def meter():
    return TokenMeter()


class TestConfigRejection:
    def test_config_none_accepted(self):
        TokenMeter(config=None)

    def test_config_empty_dict_accepted(self):
        TokenMeter(config={})

    def test_config_rejected(self):
        with pytest.raises(ValueError, match="不接受配置项"):
            TokenMeter(config={"key": "value"})


class TestEstimate:
    def test_estimate_text_empty(self, meter):
        assert meter.estimate_text("") == 0

    def test_estimate_text_basic(self, meter):
        assert meter.estimate_text("abcd") == 1

    def test_estimate_non_negative(self, meter):
        assert meter.estimate(None) >= 0
        assert meter.estimate("") >= 0
        assert meter.estimate("hello") >= 0
        assert meter.estimate({"role": "user", "content": "hi"}) >= 0

    def test_estimate_delegates_to_estimate_message(self, meter):
        msg = {"role": "user", "content": "abcd"}
        from src.core.token_meter.estimate import estimate_message
        assert meter.estimate(msg) == estimate_message(msg)


class TestGetContextWindow:
    def test_none_returns_default(self, meter):
        assert meter.get_context_window(None) == DEFAULT_CONTEXT_WINDOW

    def test_default_value(self):
        assert DEFAULT_CONTEXT_WINDOW == 32768

    def test_route_with_context_window(self, meter):
        class Route:
            context_window = 128000

        assert meter.get_context_window(Route()) == 128000

    def test_route_without_context_window(self, meter):
        class Route:
            pass

        assert meter.get_context_window(Route()) == DEFAULT_CONTEXT_WINDOW


class TestMeasure:
    @pytest.mark.asyncio
    async def test_no_store_returns_empty(self, meter):
        result = await meter.measure("session-1")
        assert result.total_tokens == 0
        assert result.surface_tokens == 0
        assert result.nodes == ()

    @pytest.mark.asyncio
    async def test_with_store(self, meter):
        class FakeStore:
            async def read_surface_events(self, session_id):
                return [
                    {"message": {"role": "user", "content": "abcd"}},
                    {"message": {"role": "assistant", "content": "efgh"}},
                ]

        meter._set_store(FakeStore())
        result = await meter.measure("session-1")
        assert result.surface_tokens > 0
        assert len(result.nodes) == 2
        assert result.baseline.kind == "estimated"

    @pytest.mark.asyncio
    async def test_store_failure_returns_empty(self, meter):
        class BadStore:
            async def read_surface_events(self, session_id):
                raise RuntimeError("store error")

        meter._set_store(BadStore())
        result = await meter.measure("session-1")
        assert result.total_tokens == 0
        assert result.nodes == ()

    @pytest.mark.asyncio
    async def test_returns_independent_snapshot(self, meter):
        class FakeStore:
            async def read_surface_events(self, session_id):
                return [{"message": {"role": "user", "content": "abcd"}}]

        meter._set_store(FakeStore())
        r1 = await meter.measure("s1")
        r2 = await meter.measure("s1")
        assert r1 == r2
        assert r1 is not r2


class TestSingleton:
    def test_get_before_init_raises(self):
        import src.core.token_meter.service as svc
        original = svc._instance
        svc._instance = None
        try:
            with pytest.raises(RuntimeError, match="未接线"):
                get_token_meter()
        finally:
            svc._instance = original

    def test_set_and_get(self):
        import src.core.token_meter.service as svc
        original = svc._instance
        m = TokenMeter()
        _set_instance(m)
        try:
            assert get_token_meter() is m
        finally:
            svc._instance = original