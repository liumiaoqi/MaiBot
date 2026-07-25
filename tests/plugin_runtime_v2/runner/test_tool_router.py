"""Task 2.3: ToolRouter 单元测试。"""

from __future__ import annotations

import asyncio
import json

import pytest

from src.plugin_runtime_v2.runner.tool_router import ToolRouter
from src.plugin_runtime_v2.sdk.decorators import ToolDeclaration
from src.plugin_runtime_v2.sdk.plugin import MaiBotPlugin


class FakePlugin(MaiBotPlugin):
    plugin_id = "test.plugin"


@pytest.fixture
def router() -> ToolRouter:
    return ToolRouter()


@pytest.fixture
def plugin() -> FakePlugin:
    return FakePlugin()


class TestRegisterUnregister:
    def test_register_and_has(self, router, plugin):
        router.register("t1", plugin, lambda p, a: a)
        assert router.has("t1")
        assert not router.has("t2")

    def test_unregister(self, router, plugin):
        router.register("t1", plugin, lambda p, a: a)
        router.unregister("t1")
        assert not router.has("t1")

    def test_unregister_nonexistent_no_error(self, router):
        router.unregister("ghost")


class TestExecuteSuccess:
    def test_execute_returns_result(self, router, plugin):
        async def handler(plg, args):
            return {"ok": True}
        router.register("ok", plugin, handler)
        loop = asyncio.get_event_loop()
        resp = loop.run_until_complete(router.execute("ok", {}))
        assert resp.success
        assert json.loads(resp.result) == {"ok": True}

    def test_execute_sync_handler(self, router, plugin):
        def handler(plg, args):
            return {"sync": True}
        router.register("sync", plugin, handler)
        loop = asyncio.get_event_loop()
        resp = loop.run_until_complete(router.execute("sync", {}))
        assert resp.success
        assert json.loads(resp.result) == {"sync": True}


class TestExecuteErrors:
    def test_tool_not_found(self, router):
        loop = asyncio.get_event_loop()
        resp = loop.run_until_complete(router.execute("ghost", {}))
        assert not resp.success
        assert resp.error == "TOOL_NOT_FOUND"

    def test_timeout(self, router, plugin):
        async def slow(plg, args):
            await asyncio.sleep(10)
        router.register("slow", plugin, slow)
        loop = asyncio.get_event_loop()
        resp = loop.run_until_complete(router.execute("slow", {}, timeout_ms=10))
        assert not resp.success
        assert resp.error == "TIMEOUT"

    def test_execution_error(self, router, plugin):
        async def broken(plg, args):
            raise RuntimeError("boom")
        router.register("broken", plugin, broken)
        loop = asyncio.get_event_loop()
        resp = loop.run_until_complete(router.execute("broken", {}))
        assert not resp.success
        assert "EXECUTION_ERROR" in resp.error
        assert "RuntimeError" in resp.error

    def test_parameter_validation_failed(self, router, plugin):
        schema = {"type": "object", "properties": {"x": {"type": "integer"}}, "required": ["x"]}
        async def handler(plg, args):
            return args
        router.register("validated", plugin, handler, ToolDeclaration(
            name="validated", description="", parameters_schema=schema,
        ))
        loop = asyncio.get_event_loop()
        resp = loop.run_until_complete(router.execute("validated", {}))
        assert not resp.success
        assert "PARAMETER_VALIDATION_FAILED" in resp.error
