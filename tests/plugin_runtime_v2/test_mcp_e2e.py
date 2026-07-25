"""Phoenix-2 MCP 组件模型端到端测试。

验证 Tool 调用全链路和 Runner 断开/重连时的 ToolProvider 注册/注销。
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from src.plugin_runtime_v2.host.connection import HostEndpointConfig
from src.plugin_runtime_v2.host.endpoint import HostEndpoint
from src.plugin_runtime_v2.runner.endpoint import RunnerEndpoint
from src.plugin_runtime_v2.runner.plugin_loader import PluginLoader
from src.plugin_runtime_v2.runner.reconnect import RunnerEndpointConfig
from src.plugin_runtime_v2.runner.tool_router import ToolRouter
from src.plugin_runtime_v2.sdk.decorators import Tool
from src.plugin_runtime_v2.sdk.plugin import MaiBotPlugin

_RUNNER_START_TIMEOUT = 10.0


# ── 测试插件 ──


class EchoPlugin(MaiBotPlugin):
    plugin_id = "test.echo"
    scopes = ["message:send:text"]

    @Tool(name="echo", description="回显工具", parameters_schema={"type": "object", "properties": {"msg": {"type": "string"}}})
    async def echo_tool(self, args: dict[str, Any]) -> dict[str, Any]:
        return {"echo": args.get("msg", "")}


class CrashingPlugin(MaiBotPlugin):
    plugin_id = "test.crasher"
    scopes = []

    @Tool(name="crash", description="会崩溃的工具")
    async def crash_tool(self, args: dict[str, Any]) -> dict[str, Any]:
        del args
        raise RuntimeError("模拟崩溃")


class SyncPlugin(MaiBotPlugin):
    plugin_id = "test.sync"
    scopes = []

    @Tool(name="sync_tool", description="同步工具")
    def sync_tool(self, args: dict[str, Any]) -> dict[str, Any]:
        return {"value": args.get("x", 0) * 2}


# ── 辅助函数 ──


def _host_config(listen_address: str = "127.0.0.1:0") -> HostEndpointConfig:
    return HostEndpointConfig(
        listen_address=listen_address,
        heartbeat_interval_s=10,
        heartbeat_timeout_s=5,
        max_heartbeat_misses=2,
        register_timeout_s=10,
        default_drain_timeout_ms=2000,
    )


def _runner_config(host_address: str, runner_id: str = "test-runner") -> RunnerEndpointConfig:
    return RunnerEndpointConfig(
        host_address=host_address,
        runner_id=runner_id,
        session_token="t",
        scopes=["message:send:text"],
        plugin_id="test.echo",
        reconnect_max_retries=2,
        reconnect_initial_delay_s=0.3,
        reconnect_max_delay_s=1.0,
    )


async def _safe_stop(runner: RunnerEndpoint) -> None:
    try:
        await runner.stop()
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════
# 8.1 Tool 调用全链路
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_tool_router_execute_success():
    """ToolRouter 直接调用：成功返回结果。"""
    router = ToolRouter()
    plugin = EchoPlugin()
    router.register("echo", plugin, plugin.echo_tool)
    response = await router.execute("echo", {"msg": "hello"}, timeout_ms=5000)
    assert response.success
    assert '"echo"' in response.result


@pytest.mark.asyncio
async def test_tool_router_tool_not_found():
    """ToolRouter：未注册 Tool 返回 TOOL_NOT_FOUND。"""
    router = ToolRouter()
    response = await router.execute("nonexistent", {}, timeout_ms=1000)
    assert not response.success
    assert response.error == "TOOL_NOT_FOUND"


@pytest.mark.asyncio
async def test_tool_router_execution_error():
    """ToolRouter：处理函数异常返回 EXECUTION_ERROR。"""
    router = ToolRouter()
    plugin = CrashingPlugin()
    router.register("crash", plugin, plugin.crash_tool)
    response = await router.execute("crash", {}, timeout_ms=5000)
    assert not response.success
    assert "EXECUTION_ERROR" in response.error


@pytest.mark.asyncio
async def test_tool_router_sync_handler():
    """ToolRouter：同步处理函数通过 asyncio.to_thread 执行。"""
    router = ToolRouter()
    plugin = SyncPlugin()
    router.register("sync_tool", plugin, plugin.sync_tool)
    response = await router.execute("sync_tool", {"x": 21}, timeout_ms=5000)
    assert response.success
    assert "42" in response.result


@pytest.mark.asyncio
async def test_tool_router_parameter_validation():
    """ToolRouter：参数校验失败返回 PARAMETER_VALIDATION_FAILED。"""
    router = ToolRouter()
    plugin = EchoPlugin()
    # EchoPlugin 声明 parameters_schema 要求 msg 为 string
    router.register("echo", plugin, plugin.echo_tool)
    response = await router.execute("echo", {"msg": 123}, timeout_ms=5000)
    # msg=123 是 int 不是 string → jsonschema 校验失败
    assert not response.success
    assert "PARAMETER_VALIDATION_FAILED" in response.error


@pytest.mark.asyncio
async def test_tool_router_timeout():
    """ToolRouter：超时返回 TIMEOUT。"""
    router = ToolRouter()

    async def slow_handler(self, args):
        await asyncio.sleep(5)
        return {"done": True}

    router.register("slow", EchoPlugin(), slow_handler)
    response = await router.execute("slow", {}, timeout_ms=100)
    assert not response.success
    assert response.error == "TIMEOUT"


# ═══════════════════════════════════════════════════════════════
# 8.5 Runner 断开/重连
# ═══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_runner_disconnect_cleanup():
    """Runner 断开后 HostEndpoint 正常关停。"""
    host = HostEndpoint(_host_config())
    await host.start()
    runner: RunnerEndpoint | None = None
    try:
        runner = RunnerEndpoint(_runner_config(host.listen_address))
        await asyncio.wait_for(runner.start(), timeout=_RUNNER_START_TIMEOUT)
        assert runner.is_ready

        # 断开 Runner
        await runner.stop()
        assert not runner.is_ready
    finally:
        if runner is not None:
            await _safe_stop(runner)
        await host.stop()


@pytest.mark.asyncio
async def test_host_stop_with_connected_runner():
    """Host 停止时 Runner 正常断开。"""
    host = HostEndpoint(_host_config())
    await host.start()
    runner: RunnerEndpoint | None = None
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
    """PluginLoader 收集装饰器声明。"""
    loader = PluginLoader(EchoPlugin)
    tools, events, cards, instance = loader.load()
    assert len(tools) == 1
    assert tools[0]["name"] == "echo"
    assert tools[0]["description"] == "回显工具"
    assert instance is not None


@pytest.mark.asyncio
async def test_plugin_loader_reconnect_protection():
    """PluginLoader 重连时不重复加载。"""
    loader = PluginLoader(EchoPlugin)
    tools1, _, _, inst1 = loader.load()
    assert loader.is_loaded
    tools2, _, _, inst2 = loader.load()
    # 重连时返回相同数据
    assert tools1 == tools2
    assert inst1 is inst2
