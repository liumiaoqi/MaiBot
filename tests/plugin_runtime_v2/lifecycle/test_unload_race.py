"""竞态集成测试 — ZG-15 T8（确定性交错构造）。

方法（design §2.1.3.4）：asyncio.Event/Barrier/Future 精确控制 task resume 点，
禁止 asyncio.sleep(0) 控制交错。验证不变量（refcount/state/acquire 结果），
不断言执行顺序。

场景：A Tool 执行中+卸载 / B reload 排空 / C shutdown 排空 + 边界异常。
"""

import asyncio

import pytest

from src.plugin_runtime_v2.lifecycle.refcount import (
    PluginHandle,
    PluginRefcount,
    PluginState,
)


class DummyPlugin:
    """可栅栏控制的测试插件。"""

    def __init__(self) -> None:
        self.plugin_id = "p1"
        self.unloaded = False

    async def on_unload(self) -> None:
        self.unloaded = True


class DummyLoader:
    """最小 loader（unload 调 on_unload）。"""

    def __init__(self, plugin: DummyPlugin) -> None:
        self._plugin = plugin
        self.instance = plugin

    async def unload(self, plugin: DummyPlugin) -> None:
        await plugin.on_unload()


# ── 场景 A：Tool 执行中 + 卸载（handler 与 unloader 确定性交错）────────

@pytest.mark.asyncio
async def test_race_A_tool_execute_vs_unload() -> None:
    """handler await 期间 mark_going → 在途完成、新 acquire 失败、排空归零。

    栅栏：handler_entered（handler 已 acquire）/ release_handler（main 放行
    handler 完成）。unloader 等 handler_entered 后 mark_going——此时 handler
    持有引用，必须 wait_drained 等到 release 才归零。
    """
    plugin = DummyPlugin()
    rc = PluginRefcount("p1")
    handle = PluginHandle(plugin, rc)

    handler_entered = asyncio.Event()
    release_handler = asyncio.Event()
    going_set = asyncio.Event()

    async def slow_handler() -> str:
        async with handle.acquire(tool_name="slow") as h:
            assert h is plugin
            handler_entered.set()
            await release_handler.wait()  # 在途保持直到放行
            return "done"

    async def unloader() -> None:
        await handler_entered.wait()  # handler 已 acquire（refcount=1）
        assert rc.mark_going() is False  # 有在途 → 需排空
        going_set.set()
        drained = await rc.wait_drained(timeout_s=5.0)  # 等 handler release
        assert drained is True

    task_handler = asyncio.create_task(slow_handler())
    task_unloader = asyncio.create_task(unloader())
    await going_set.wait()  # GOING 已设

    # 不变量 1：GOING 后新 acquire 必须失败
    assert rc.try_acquire() is False
    # 不变量 2：在途 handler 仍在执行（引用未释放）
    assert rc.refcount == 1
    assert not task_handler.done()

    # 放行 handler → release → 排空完成
    release_handler.set()
    assert await task_handler == "done"
    await task_unloader
    assert rc.refcount == 0
    assert rc.state == PluginState.GOING  # 卸载流程未 mark_unformed（原语级验证）


# ── 场景 B：reload 排空（GetInflightCount 递减计数）──────────────────

@pytest.mark.asyncio
async def test_race_B_reload_drain_polls_to_zero() -> None:
    """reload 轮询 GetInflightCount 至零后才杀进程 + spawn。"""
    import types

    from src.plugin_runtime_v2.host.runner_supervisor import (
    RunnerSupervisor,
    RunnerSupervisorConfig,
)

    sv = RunnerSupervisor(
        RunnerSupervisorConfig(drain_ms=5000), object(), host_listen_address="localhost:0")

    poll_calls = 0

    async def fake_poll(self, runner_id: str, address: str, drain_ms: int) -> bool:
        nonlocal poll_calls
        poll_calls += 1
        return True  # 模拟计数轮询至零

    sv._poll_inflight = types.MethodType(fake_poll, sv)  # type: ignore[method-assign]
    sv._spawner.kill_runner = _async_return(True)
    sv._spawner.spawn = _async_return(_FakeProc())
    sv._spawner._plugin_dirs = {"r1": "plugins/p"}

    mock_conn = types.SimpleNamespace(state=types.SimpleNamespace(value="ready"),
                                      runner_listen_address="localhost:9999")
    sv._registry = types.SimpleNamespace(get=lambda _rid: mock_conn,
                                         unregister=lambda _rid: None)
    sv._log_forwarders = {}
    sv._servicer = types.SimpleNamespace(request_shutdown=lambda *a, **k: None)

    result = await sv.reload_one("r1")
    assert result.success is True
    assert poll_calls >= 1  # 至少轮询一次


@pytest.mark.asyncio
async def test_race_B_unavailable_means_drained() -> None:
    """GetInflightCount 返回 UNAVAILABLE（进程死）→ 视为已排空直接重启。"""
    import types

    from src.plugin_runtime_v2.host.runner_supervisor import (
    RunnerSupervisor,
    RunnerSupervisorConfig,
)

    sv = RunnerSupervisor(
        RunnerSupervisorConfig(drain_ms=5000), object(), host_listen_address="localhost:0")

    async def fake_poll(self, runner_id: str, address: str, drain_ms: int) -> bool:
        return True  # 模拟 UNAVAILABLE 已排空

    sv._poll_inflight = types.MethodType(fake_poll, sv)  # type: ignore[method-assign]
    sv._spawner.kill_runner = _async_return(True)
    sv._spawner.spawn = _async_return(_FakeProc())
    sv._spawner._plugin_dirs = {"r1": "plugins/p"}
    mock_conn = types.SimpleNamespace(state=types.SimpleNamespace(value="ready"),
                                      runner_listen_address="")
    sv._registry = types.SimpleNamespace(get=lambda _rid: mock_conn,
                                         unregister=lambda _rid: None)
    sv._log_forwarders = {}
    sv._servicer = types.SimpleNamespace(request_shutdown=lambda *a, **k: None)

    result = await sv.reload_one("r1")
    assert result.success is True


def _async_return(value):
    async def _inner(*args, **kwargs):
        return value
    return _inner


# ── 场景 C：shutdown 排空（PluginUnloader 全流程与在途 handler 交错）──

@pytest.mark.asyncio
async def test_race_C_shutdown_drain() -> None:
    """unload_plugin 全流程：mark_going → wait_drained（在途完成）→ on_unload。"""
    from src.plugin_runtime_v2.lifecycle.unloader import PluginUnloader

    plugin = DummyPlugin()
    rc = PluginRefcount("p1")
    loader = DummyLoader(plugin)
    handle = PluginHandle(plugin, rc)
    unloader = PluginUnloader(rc, loader)

    handler_entered = asyncio.Event()
    release_handler = asyncio.Event()

    async def inflight() -> None:
        async with handle.acquire(tool_name="inflight"):
            handler_entered.set()
            await release_handler.wait()

    async def shutdown() -> None:
        await handler_entered.wait()
        result = await unloader.unload_plugin()  # 内部 mark_going → wait_drained
        assert result.success is True

    task = asyncio.create_task(inflight())
    task_shutdown = asyncio.create_task(shutdown())
    await asyncio.sleep(0.01)  # 让 shutdown 推进到 wait_drained（Event 栅栏后）
    assert rc.state == PluginState.GOING
    # 排空等待中：在途 handler 尚未释放
    assert rc.refcount == 1
    assert not task.done()

    release_handler.set()  # 放行 → 排空完成 → on_unload → UNFORMED
    await task
    await task_shutdown
    assert plugin.unloaded is True
    assert rc.state == PluginState.UNFORMED


# ── 边界与异常 ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_concurrent_acquire_during_going() -> None:
    """mark_going 前后并发的 acquire：结果与 refcount 一致（无 TOCTOU）。"""
    rc = PluginRefcount("p1")
    barrier = asyncio.Barrier(3)
    results: list[bool] = []

    async def racer() -> None:
        await barrier.wait()
        results.append(rc.try_acquire())

    async def marker() -> None:
        await barrier.wait()
        rc.mark_going()

    tasks = [asyncio.create_task(racer()) for _ in range(2)]
    tasks.append(asyncio.create_task(marker()))
    await asyncio.gather(*tasks)
    # 不变量：acquire 成功数 = 最终 refcount（同步段无 TOCTOU）
    assert sum(results) == rc.refcount


@pytest.mark.asyncio
async def test_double_mark_going() -> None:
    """重复 mark_going 返回当前 refcount==0（幂等）。"""
    rc = PluginRefcount("p1")
    rc.mark_going()
    assert rc.mark_going() is True
    assert rc.state == PluginState.GOING


@pytest.mark.asyncio
async def test_reload_timeout_force_kill() -> None:
    """排空超时 → 强杀旧进程 + 仍 spawn（保进度）。"""
    import types

    from src.plugin_runtime_v2.host.runner_supervisor import (
    RunnerSupervisor,
    RunnerSupervisorConfig,
)

    sv = RunnerSupervisor(
        RunnerSupervisorConfig(drain_ms=100), object(), host_listen_address="localhost:0")

    async def fake_poll(self, runner_id: str, address: str, drain_ms: int) -> bool:
        return False  # 模拟排空超时

    sv._poll_inflight = types.MethodType(fake_poll, sv)  # type: ignore[method-assign]
    sv._spawner.kill_runner = _async_return(True)
    sv._spawner.spawn = _async_return(_FakeProc())
    sv._spawner._plugin_dirs = {"r1": "plugins/p"}
    mock_conn = types.SimpleNamespace(state=types.SimpleNamespace(value="ready"),
                                      runner_listen_address="localhost:9999")
    sv._registry = types.SimpleNamespace(get=lambda _rid: mock_conn,
                                         unregister=lambda _rid: None)
    sv._log_forwarders = {}
    sv._servicer = types.SimpleNamespace(request_shutdown=lambda *a, **k: None)

    result = await sv.reload_one("r1")
    assert result.success is True  # 超时强杀后仍 spawn


class _FakeProc:
    """supervisor.spawn 需要的假进程（stdout/stderr=None 跳过日志读取）。"""

    def __init__(self) -> None:
        self.stdout = None
        self.stderr = None
        self.pid = 12345


# ── CX 审查 P0-1 回归：预置 GOING 后卸载必须继续 ─────────────────

@pytest.mark.asyncio
async def test_unload_plugin_when_already_going_continues() -> None:
    """_handle_shutdown 预置 GOING（无在途）后，unload_plugin 必须继续执行。

    CX 审查 P0-1：旧实现见 GOING 立即返回 ALREADY_GOING，
    cancel_all_tasks/on_unload/mark_unformed 全部被跳过——插件假装卸载了。
    """
    from src.plugin_runtime_v2.lifecycle.unloader import PluginUnloader

    plugin = DummyPlugin()
    rc = PluginRefcount("p1")
    loader = DummyLoader(plugin)
    rc.mark_going()  # 模拟 _handle_shutdown 预置 GOING
    unloader = PluginUnloader(rc, loader)
    result = await unloader.unload_plugin()
    assert result.success is True
    assert plugin.unloaded is True
    assert rc.state == PluginState.UNFORMED


@pytest.mark.asyncio
async def test_unload_plugin_when_going_with_inflight() -> None:
    """预置 GOING + 在途引用：unload_plugin 等待排空后继续卸载（P0-1 回归）。"""
    from src.plugin_runtime_v2.lifecycle.unloader import PluginUnloader

    plugin = DummyPlugin()
    rc = PluginRefcount("p1")
    loader = DummyLoader(plugin)
    handle = PluginHandle(plugin, rc)
    unloader = PluginUnloader(rc, loader)

    handler_entered = asyncio.Event()
    release_handler = asyncio.Event()

    async def inflight() -> None:
        async with handle.acquire(tool_name="inflight"):
            handler_entered.set()
            await release_handler.wait()

    task = asyncio.create_task(inflight())
    await handler_entered.wait()
    rc.mark_going()  # 预置 GOING（有在途）

    task_unload = asyncio.create_task(unloader.unload_plugin())
    await asyncio.sleep(0.01)  # 让 unload_plugin 进入 wait_drained
    assert rc.state == PluginState.GOING
    assert not task_unload.done()  # 排空等待中

    release_handler.set()
    await task
    result = await task_unload
    assert result.success is True
    assert plugin.unloaded is True
    assert rc.state == PluginState.UNFORMED
