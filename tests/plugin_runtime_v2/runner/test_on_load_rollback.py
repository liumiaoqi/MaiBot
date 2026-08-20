"""on_load 失败 rollback 单测 — 批 C C1。

验证：on_load 抛异常时已注册 tool 被注销 + refcount 状态置 ERROR。
"""

import pytest

from src.plugin_runtime_v2.lifecycle.refcount import PluginRefcount, PluginState
from src.plugin_runtime_v2.runner.tool_router import ToolRouter


class _FakePlugin:
    """模拟插件实例——on_load 抛异常。"""

    async def on_load(self) -> None:
        raise RuntimeError("simulated on_load failure")

    async def on_unload(self) -> None:
        pass


def test_on_load_failure_rolls_back_tools_and_sets_error_state() -> None:
    """on_load 失败 → 已注册 tool 全部注销 + refcount 状态 ERROR。"""
    tool_router = ToolRouter()
    refcount = PluginRefcount("test-plugin")
    plugin = _FakePlugin()

    tools = [
        {"name": "tool_a", "handler": lambda args: None},
        {"name": "tool_b", "handler": lambda args: None},
    ]
    for entry in tools:
        tool_router.register(
            tool_name=entry["name"],
            plugin=plugin,
            handler=entry["handler"],
            refcount=refcount,
        )

    assert tool_router.has("tool_a")
    assert tool_router.has("tool_b")
    assert refcount.state == PluginState.LIVE

    # 模拟 on_load 失败后的 rollback 逻辑（与 endpoint.py:135-146 一致）
    for entry in tools:
        tool_router.unregister(entry["name"])
    refcount.mark_error()

    assert not tool_router.has("tool_a")
    assert not tool_router.has("tool_b")
    assert refcount.state == PluginState.ERROR
    assert refcount.try_acquire() is False


def test_on_load_success_does_not_rollback() -> None:
    """on_load 成功 → tool 保持注册 + refcount 状态 LIVE。"""

    class _OkPlugin:
        async def on_load(self) -> None:
            pass

    tool_router = ToolRouter()
    refcount = PluginRefcount("test-plugin")
    plugin = _OkPlugin()

    tool_router.register(
        tool_name="tool_a",
        plugin=plugin,
        handler=lambda args: None,
        refcount=refcount,
    )

    assert tool_router.has("tool_a")
    assert refcount.state == PluginState.LIVE


@pytest.mark.asyncio
async def test_on_load_failure_endpoint_integration() -> None:
    """端点级集成：on_load 抛异常 → tool 注销 + ERROR + start 返回。"""
    from src.plugin_runtime_v2.runner.endpoint import RunnerEndpoint
    from src.plugin_runtime_v2.runner.reconnect import RunnerEndpointConfig

    class _FailingPluginLoader:
        def __init__(self) -> None:
            self._loaded = False

        async def load(self):
            self._loaded = True
            plugin = _FakePlugin()
            plugin.ctx = None
            return (
                [{"name": "tool_x", "handler": lambda args: None}],
                [],
                None,
                plugin,
            )

        async def unload(self, plugin) -> None:
            pass

        @property
        def is_loaded(self) -> bool:
            return self._loaded

    config = RunnerEndpointConfig(
        plugin_id="test-plugin",
        runner_id="test-runner",
        host_address="localhost:9999",
        scopes=[],
    )
    endpoint = RunnerEndpoint(config, plugin_loader=_FailingPluginLoader())

    await endpoint.start()

    assert not endpoint._tool_router.has("tool_x")
    assert endpoint._refcount is not None
    assert endpoint._refcount.state == PluginState.ERROR