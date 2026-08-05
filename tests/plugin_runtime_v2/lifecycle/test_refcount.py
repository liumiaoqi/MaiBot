"""PluginRefcount 单元测试 — ZG-15 T1.5。

覆盖：acquire/release 对称、GOING 拒新、下溢告警、mark_going 语义、
wait_drained 等待/超时、状态单向流转、PluginHandle 上下文管理器。
"""

import asyncio

import pytest

from src.plugin_runtime_v2.lifecycle.refcount import (
    PluginHandle,
    PluginRefcount,
    PluginState,
)


class DummyPlugin:
    def __init__(self) -> None:
        self.called = False

    async def some_tool(self, args: dict) -> str:
        self.called = True
        return "ok"


@pytest.mark.asyncio
async def test_try_acquire_live() -> None:
    """LIVE 状态 acquire 成功 + refcount 递增。"""
    rc = PluginRefcount("test-plugin")
    assert rc.state == PluginState.LIVE
    assert rc.refcount == 0
    assert rc.try_acquire(tool_name="tool_a") is True
    assert rc.refcount == 1
    assert len(rc.inflight_entries) == 1
    assert rc.inflight_entries[0].tool_name == "tool_a"
    rc.release()
    assert rc.refcount == 0


@pytest.mark.asyncio
async def test_try_acquire_going() -> None:
    """GOING 状态 acquire 失败 + refcount 不变。"""
    rc = PluginRefcount("test-plugin")
    rc.mark_going()
    assert rc.try_acquire() is False
    assert rc.refcount == 0


@pytest.mark.asyncio
async def test_release_decrement() -> None:
    """release 递减 + 归零触发 zero_event。"""
    rc = PluginRefcount("test-plugin")
    rc.try_acquire()
    rc.try_acquire()
    assert rc.refcount == 2
    rc.release()
    assert rc.refcount == 1
    rc.release()
    assert rc.refcount == 0
    assert rc._zero_event.is_set()  # 归零后事件触发


@pytest.mark.asyncio
async def test_release_underflow(caplog) -> None:
    """refcount==0 时 release 输出 WARNING、refcount 不为负。"""
    rc = PluginRefcount("test-plugin")
    with caplog.at_level("WARNING"):
        rc.release()
    assert rc.refcount == 0
    assert "下溢" in caplog.text


@pytest.mark.asyncio
async def test_mark_going_no_inflight() -> None:
    """refcount==0 时 mark_going 返回 True（可立即卸载）。"""
    rc = PluginRefcount("test-plugin")
    assert rc.mark_going() is True
    assert rc.state == PluginState.GOING


@pytest.mark.asyncio
async def test_mark_going_with_inflight() -> None:
    """refcount>0 时 mark_going 返回 False、state 变 GOING。"""
    rc = PluginRefcount("test-plugin")
    rc.try_acquire(tool_name="tool_a")
    assert rc.mark_going() is False
    assert rc.state == PluginState.GOING
    # GOING 后新 acquire 失败
    assert rc.try_acquire() is False
    # 在途 release 归零
    rc.release()
    assert rc.refcount == 0


@pytest.mark.asyncio
async def test_mark_going_idempotent() -> None:
    """重复 mark_going 返回当前 refcount==0。"""
    rc = PluginRefcount("test-plugin")
    rc.mark_going()
    assert rc.mark_going() is True
    rc.try_acquire()  # GOING 下不应成功
    assert rc.mark_going() is True  # refcount 仍为 0


@pytest.mark.asyncio
async def test_wait_drained_success() -> None:
    """release 后 zero_event 触发、wait_drained 返回 True。"""
    rc = PluginRefcount("test-plugin")
    rc.try_acquire()
    assert rc.mark_going() is False

    async def release_later() -> None:
        await asyncio.sleep(0.01)
        rc.release()

    task = asyncio.create_task(release_later())
    assert await rc.wait_drained(timeout_s=1.0) is True
    await task


@pytest.mark.asyncio
async def test_wait_drained_timeout(caplog) -> None:
    """超时返回 False + ERROR 日志（含在途详情）。"""
    rc = PluginRefcount("test-plugin")
    rc.try_acquire(tool_name="slow_tool")
    with caplog.at_level("ERROR"):
        assert await rc.wait_drained(timeout_s=0.01) is False
    assert "排空超时" in caplog.text
    assert "slow_tool" in caplog.text  # 在途详情


@pytest.mark.asyncio
async def test_state_unidirectional() -> None:
    """GOING 后不可回 LIVE、UNFORMED 后不可回任何先前状态。"""
    rc = PluginRefcount("test-plugin")
    rc.mark_going()
    assert rc.state == PluginState.GOING
    # 无回退 API——状态只由 mark_going/mark_unformed 单向推进
    rc.mark_unformed()
    assert rc.state == PluginState.UNFORMED


@pytest.mark.asyncio
async def test_handle_acquire_release_symmetry() -> None:
    """PluginHandle acquire 成功后 release 对称递减。"""
    plugin = DummyPlugin()
    rc = PluginRefcount("test-plugin")
    handle = PluginHandle(plugin, rc)
    async with handle.acquire(tool_name="tool_a") as h:
        assert h is plugin
        assert rc.refcount == 1
        result = await h.some_tool({})
        assert result == "ok"
        assert plugin.called
    assert rc.refcount == 0


@pytest.mark.asyncio
async def test_handle_acquire_going_yields_none() -> None:
    """GOING 状态 handle.acquire() yield None、不调 release。"""
    plugin = DummyPlugin()
    rc = PluginRefcount("test-plugin")
    rc.mark_going()
    handle = PluginHandle(plugin, rc)
    async with handle.acquire() as h:
        assert h is None
    assert rc.refcount == 0
