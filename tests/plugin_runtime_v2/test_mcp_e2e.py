"""Phoenix-2 MCP 组件模型端到端测试。"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.plugin_runtime_v2.host.connection import HostEndpointConfig
from src.plugin_runtime_v2.host.endpoint import HostEndpoint
from src.plugin_runtime_v2.runner.endpoint import RunnerEndpoint
from src.plugin_runtime_v2.runner.plugin_loader import PluginLoader
from src.plugin_runtime_v2.runner.reconnect import RunnerEndpointConfig
from src.plugin_runtime_v2.runner.tool_router import ToolRouter
from src.plugin_runtime_v2.sdk.context import PluginContext
from src.plugin_runtime_v2.sdk.decorators import HomeCard, Tool
from src.plugin_runtime_v2.sdk.plugin import MaiBotPlugin

_RUNNER_START_TIMEOUT = 10.0


class EchoPlugin(MaiBotPlugin):
    plugin_id = "test.echo"
    scopes = ["message:send:text"]

    @Tool(name="echo", description="回显工具", parameters_schema={"type": "object", "properties": {"msg": {"type": "string"}}})
    async def echo_tool(self, args):
        return {"echo": args.get("msg", "")}


class CrashingPlugin(MaiBotPlugin):
    plugin_id = "test.crasher"
    scopes = []

    @Tool(name="crash", description="会崩溃的工具")
    async def crash_tool(self, args):
        del args
        raise RuntimeError("模拟崩溃")


class SyncPlugin(MaiBotPlugin):
    plugin_id = "test.sync"
    scopes = []

    @Tool(name="sync_tool", description="同步工具")
    def sync_tool(self, args):
        return {"value": args.get("x", 0) * 2}


class CardPlugin(MaiBotPlugin):
    plugin_id = "test.card"

    @HomeCard(name="dashboard", title="控制台", width="wide")
    async def dashboard_card(self):
        pass


class CtxInjectPlugin(MaiBotPlugin):
    plugin_id = "test.ctxinject"
    scopes = ["message:send:text"]

    @Tool(name="cmd_help", description="命令帮助", parameters_schema={"type": "object", "properties": {}})
    async def cmd_help(self, args):
        return {"session": args.get("session_id", ""), "sender": args.get("sender_id", "")}


def _host_config(listen_address: str = "127.0.0.1:0") -> HostEndpointConfig:
    return HostEndpointConfig(listen_address=listen_address, register_timeout_s=10, default_drain_timeout_ms=2000)


def _runner_config(host_address: str, runner_id: str = "test-runner") -> RunnerEndpointConfig:
    return RunnerEndpointConfig(
        host_address=host_address, runner_id=runner_id, session_token="t",
        scopes=["message:send:text"], plugin_id="test.echo",
        reconnect_max_retries=2, reconnect_initial_delay_s=0.3, reconnect_max_delay_s=1.0,
    )


async def _safe_stop(runner) -> None:
    try:
        await runner.stop()
    except Exception:
        pass


# ═══════════════════════════════════════════════════
# 8.1 Tool 调用
# ═══════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_tool_router_execute_success():
    router = ToolRouter()
    plugin = EchoPlugin()
    router.register("echo", plugin, plugin.echo_tool)
    response = await router.execute("echo", {"msg": "hello"}, timeout_ms=5000)
    assert response.success

@pytest.mark.asyncio
async def test_tool_router_tool_not_found():
    router = ToolRouter()
    response = await router.execute("nonexistent", {}, timeout_ms=1000)
    assert not response.success
    assert response.error == "TOOL_NOT_FOUND"

@pytest.mark.asyncio
async def test_tool_router_execution_error():
    router = ToolRouter()
    plugin = CrashingPlugin()
    router.register("crash", plugin, plugin.crash_tool)
    response = await router.execute("crash", {}, timeout_ms=5000)
    assert not response.success
    assert "EXECUTION_ERROR" in response.error

@pytest.mark.asyncio
async def test_tool_router_sync_handler():
    router = ToolRouter()
    plugin = SyncPlugin()
    router.register("sync_tool", plugin, plugin.sync_tool)
    response = await router.execute("sync_tool", {"x": 21}, timeout_ms=5000)
    assert response.success
    assert "42" in response.result

@pytest.mark.asyncio
async def test_tool_router_parameter_validation():
    router = ToolRouter()
    plugin = EchoPlugin()
    router.register("echo", plugin, plugin.echo_tool)
    response = await router.execute("echo", {"msg": 123}, timeout_ms=5000)
    assert not response.success
    assert "PARAMETER_VALIDATION_FAILED" in response.error

@pytest.mark.asyncio
async def test_tool_router_timeout():
    router = ToolRouter()
    async def slow_handler(self, args):
        await asyncio.sleep(5)
        return {"done": True}
    router.register("slow", EchoPlugin(), slow_handler)
    response = await router.execute("slow", {}, timeout_ms=100)
    assert not response.success
    assert response.error == "TIMEOUT"


# ═══════════════════════════════════════════════════
# 8.2 Event 推送
# ═══════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_event_push_chain():
    host = HostEndpoint(_host_config())
    await host.start()
    runner = None
    try:
        runner = RunnerEndpoint(_runner_config(host.listen_address))
        await asyncio.wait_for(runner.start(), timeout=_RUNNER_START_TIMEOUT)
        assert runner.is_ready
        with patch("src.plugin_runtime_v2.mcp.event_dispatcher.logger.info") as mock_info:
            await runner.emit_event("custom_event", {"key": "val"})
            await asyncio.sleep(0.5)
            found = any("custom_event" in str(c) for c in mock_info.call_args_list)
            assert found
    finally:
        if runner is not None:
            await _safe_stop(runner)
        await host.stop()


# ═══════════════════════════════════════════════════
# 8.3 @Command 上下文注入
# ═══════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_command_context_injection_chain():
    from src.core.tooling import ToolInvocation, ToolExecutionContext, ToolRegistry
    from src.plugin_runtime_v2.mcp.host_bridge import MCPHostBridge
    from src.plugin_runtime_v2.mcp.event_dispatcher import EventDispatcher

    router = ToolRouter()
    plugin = CtxInjectPlugin()
    router.register("cmd_help", plugin, plugin.cmd_help)

    bridge = MCPHostBridge(ToolRegistry(), EventDispatcher(), MagicMock())
    inv = ToolInvocation(tool_name="cmd_help", arguments={}, call_id="c1", session_id="")
    ctx = ToolExecutionContext(session_id="sid1", user_id="uid1", is_group_chat=True)
    bridge._inject_command_context(inv, ctx, {"pattern": "/help"})

    resp = await router.execute("cmd_help", inv.arguments)
    assert resp.success
    result = json.loads(resp.result)
    assert result["session"] == "sid1"
    assert result["sender"] == "uid1"


# ═══════════════════════════════════════════════════
# 8.4 HomeCard 推送
# ═══════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_homecard_push_chain():
    loader = PluginLoader(CardPlugin)
    tools, events, cards, instance = await loader.load()
    assert "dashboard" in cards
    assert cards["dashboard"]["title"] == "控制台"
    assert cards["dashboard"]["width"] == "wide"

    runner = AsyncMock()
    runner.is_ready = True
    ctx = PluginContext("test.card", set(), runner, cards)
    await ctx.emit_card("dashboard", {"score": 100})
    payload = runner.emit_event.call_args[0][1]
    assert payload["name"] == "dashboard"
    assert payload["title"] == "控制台"
    assert payload["width"] == "wide"
    assert payload["data"] == {"score": 100}


# ═══════════════════════════════════════════════════
# 8.5 Runner 断开/重连 + PluginLoader
# ═══════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_runner_disconnect_cleanup():
    host = HostEndpoint(_host_config())
    await host.start()
    runner = None
    try:
        runner = RunnerEndpoint(_runner_config(host.listen_address))
        await asyncio.wait_for(runner.start(), timeout=_RUNNER_START_TIMEOUT)
        assert runner.is_ready
        await runner.stop()
        assert not runner.is_ready
    finally:
        if runner is not None:
            await _safe_stop(runner)
        await host.stop()

@pytest.mark.asyncio
async def test_host_stop_with_connected_runner():
    host = HostEndpoint(_host_config())
    await host.start()
    runner = None
    try:
        runner = RunnerEndpoint(_runner_config(host.listen_address))
        await asyncio.wait_for(runner.start(), timeout=_RUNNER_START_TIMEOUT)
        assert runner.is_ready
    finally:
        if runner is not None:
            await _safe_stop(runner)
        await host.stop()
    assert host.get_status() == {}

@pytest.mark.asyncio
async def test_plugin_loader_collects_declarations():
    loader = PluginLoader(EchoPlugin)
    tools, events, cards, instance = await loader.load()
    assert len(tools) == 1
    assert tools[0]["name"] == "echo"
    assert instance is not None

@pytest.mark.asyncio
async def test_plugin_loader_reconnect_protection():
    loader = PluginLoader(EchoPlugin)
    tools1, _, _, inst1 = await loader.load()
    assert loader.is_loaded
    tools2, _, _, inst2 = await loader.load()
    assert tools1 == tools2
    assert inst1 is inst2
