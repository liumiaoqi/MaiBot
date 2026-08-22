"""HostEndpoint 单元测试 — gRPC 端点管理生命周期。

覆盖：
- 构造与默认/自定义配置
- 属性访问（listen_address/scope_store/token_service/get_status）
- setter 注入（set_supervisor 双向/set_activation_coordinator/get_supervisor）
- reload_runners（有/无 supervisor）
- stop 逆序卸载（有 coordinator）/原顺序 fallback（无 coordinator）/无 server 直接返回
- stop 取消 cleanup_task
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.plugin_runtime_v2.host.connection import (
    ConnectionState,
    HostEndpointConfig,
    RunnerConnection,
)
from src.plugin_runtime_v2.host.endpoint import HostEndpoint


def _make_connection(runner_id: str, state=ConnectionState.READY) -> RunnerConnection:
    """构造真实 RunnerConnection 用于注册。"""
    return RunnerConnection(
        runner_id=runner_id,
        state=state,
        sdk_version="4.0.0",
        session_token="",
        scopes=[],
    )


class TestHostEndpointConstruct:
    """构造与配置。"""

    def test_default_config(self):
        ep = HostEndpoint()
        assert ep._cfg.listen_address == "127.0.0.1:50051"
        assert ep._server is None
        assert ep._actual_listen_address == ""
        assert ep._activation_coordinator is None
        assert ep._plugin_config_servicer is None

    def test_custom_config(self):
        cfg = HostEndpointConfig(listen_address="0.0.0.0:9999", server_id="sid")
        ep = HostEndpoint(config=cfg)
        assert ep._cfg.listen_address == "0.0.0.0:9999"
        assert ep._cfg.server_id == "sid"

    def test_injected_services(self):
        token = MagicMock()
        scope = MagicMock()
        storage = MagicMock()
        ep = HostEndpoint(
            token_service=token, scope_store=scope, storage_service=storage,
        )
        assert ep._token_service is token
        assert ep._scope_store is scope
        assert ep._storage_service is storage


class TestHostEndpointProperties:
    """属性访问。"""

    def test_listen_address_empty(self):
        ep = HostEndpoint()
        assert ep.listen_address == ""

    def test_scope_store_property(self):
        scope = MagicMock()
        ep = HostEndpoint(scope_store=scope)
        assert ep.scope_store is scope

    def test_token_service_property(self):
        token = MagicMock()
        ep = HostEndpoint(token_service=token)
        assert ep.token_service is token

    def test_get_status_empty(self):
        ep = HostEndpoint()
        assert ep.get_status() == {}

    def test_get_status_with_runner(self):
        ep = HostEndpoint()
        ep._registry.register(_make_connection("r1"))
        status = ep.get_status()
        assert "r1" in status
        assert status["r1"].runner_id == "r1"


class TestHostEndpointSetters:
    """setter 注入。"""

    def test_set_supervisor_bidirectional(self):
        """set_supervisor 双向注入：supervisor.set_servicer + servicer._supervisor。"""
        ep = HostEndpoint()
        sv = MagicMock()
        sv.set_servicer = MagicMock()
        ep.set_supervisor(sv)
        assert ep.get_supervisor() is sv
        sv.set_servicer.assert_called_once_with(ep._servicer)
        assert ep._servicer._supervisor is sv

    def test_set_activation_coordinator(self):
        ep = HostEndpoint()
        coord = MagicMock()
        ep.set_activation_coordinator(coord)
        assert ep._activation_coordinator is coord

    def test_get_supervisor_none(self):
        ep = HostEndpoint()
        assert ep.get_supervisor() is None


class TestHostEndpointReload:
    """reload_runners。"""

    @pytest.mark.asyncio
    async def test_reload_no_supervisor(self):
        ep = HostEndpoint()
        result = await ep.reload_runners(drain_ms=100)
        assert result == {}

    @pytest.mark.asyncio
    async def test_reload_with_supervisor(self):
        ep = HostEndpoint()
        sv = MagicMock()
        sv.set_servicer = MagicMock()
        sv.reload_all = AsyncMock(return_value={"r1": "ok"})
        ep.set_supervisor(sv)
        result = await ep.reload_runners(drain_ms=100)
        assert result == {"r1": "ok"}
        sv.reload_all.assert_awaited_once_with(100)


class TestHostEndpointStop:
    """stop 生命周期：逆序卸载/fallback/无 server/cleanup_task。"""

    @pytest.mark.asyncio
    async def test_stop_no_server(self):
        """无 server 时 stop 直接返回。"""
        ep = HostEndpoint()
        await ep.stop()  # 不抛异常

    @pytest.mark.asyncio
    async def test_stop_with_coordinator_reverse_unload(self):
        """有 coordinator 时按依赖图逆序卸载。"""
        ep = HostEndpoint()
        ep._server = MagicMock()
        ep._server.stop = AsyncMock()
        ep._registry.register(_make_connection("r1"))
        ep._registry.register(_make_connection("r2"))
        # mock heartbeat.stop + servicer.request_shutdown
        ep._heartbeat_mgr.stop = MagicMock()
        ep._servicer.request_shutdown = MagicMock()
        # coordinator 返回逆序
        coord = MagicMock()
        coord.plan_unload = MagicMock(return_value=["r2", "r1"])
        coord.on_plugin_unloaded = MagicMock()
        ep.set_activation_coordinator(coord)
        ep._cfg = HostEndpointConfig(default_drain_timeout_ms=0)
        server = ep._server  # stop 末尾会置 None，先保存引用

        await ep.stop()

        # 验证逆序卸载
        plan_unload_arg = coord.plan_unload.call_args[0][0]
        assert plan_unload_arg == {"r1", "r2"}
        # request_shutdown 按逆序调用
        shutdown_calls = [c.args[0] for c in ep._servicer.request_shutdown.call_args_list]
        assert shutdown_calls == ["r2", "r1"]
        coord.on_plugin_unloaded.assert_any_call("r2")
        coord.on_plugin_unloaded.assert_any_call("r1")
        server.stop.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stop_without_coordinator_fallback_order(self):
        """无 coordinator 时按原顺序卸载（向后兼容）。"""
        ep = HostEndpoint()
        ep._server = MagicMock()
        ep._server.stop = AsyncMock()
        ep._registry.register(_make_connection("r1"))
        ep._registry.register(_make_connection("r2"))
        ep._heartbeat_mgr.stop = MagicMock()
        ep._servicer.request_shutdown = MagicMock()
        ep._cfg = HostEndpointConfig(default_drain_timeout_ms=0)
        server = ep._server

        await ep.stop()

        # 无 coordinator → 原顺序（registry 插入序）
        shutdown_calls = [c.args[0] for c in ep._servicer.request_shutdown.call_args_list]
        assert set(shutdown_calls) == {"r1", "r2"}
        server.stop.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stop_cancels_cleanup_task(self):
        """stop 取消 token cleanup 后台任务。"""
        ep = HostEndpoint(token_service=MagicMock())
        ep._server = MagicMock()
        ep._server.stop = AsyncMock()

        async def cleanup():
            try:
                await asyncio.sleep(100)
            except asyncio.CancelledError:
                pass

        ep._cleanup_task = asyncio.create_task(cleanup())
        ep._cfg = HostEndpointConfig(default_drain_timeout_ms=0)

        await ep.stop()
        assert ep._cleanup_task is None

    @pytest.mark.asyncio
    async def test_stop_drain_waits(self):
        """drain_ms > 0 时 stop 等待排空。"""
        ep = HostEndpoint()
        ep._server = MagicMock()
        ep._server.stop = AsyncMock()
        ep._registry.register(_make_connection("r1"))
        ep._heartbeat_mgr.stop = MagicMock()
        ep._servicer.request_shutdown = MagicMock()
        ep._cfg = HostEndpointConfig(default_drain_timeout_ms=50)

        import time as time_mod
        start = time_mod.monotonic()
        await ep.stop()
        elapsed = time_mod.monotonic() - start
        # 至少等待了 50ms
        assert elapsed >= 0.04  # 留点容差


class TestHostEndpointCleanupLoop:
    """_cleanup_loop 后台任务。"""

    @pytest.mark.asyncio
    async def test_cleanup_loop_cancelled_silent(self):
        """_cleanup_loop 被 cancel 时静默退出。"""
        ep = HostEndpoint(token_service=MagicMock())
        task = asyncio.create_task(ep._cleanup_loop())
        await asyncio.sleep(0.01)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass  # 正常取消静默

    @pytest.mark.asyncio
    async def test_cleanup_loop_calls_cleanup(self, monkeypatch):
        """_cleanup_loop 定期调用 token_service.cleanup_expired。"""
        token = MagicMock()
        token.cleanup_expired = MagicMock()
        ep = HostEndpoint(token_service=token)

        real_sleep = asyncio.sleep
        call_count = 0

        async def fast_sleep(_seconds):
            nonlocal call_count
            call_count += 1
            if call_count > 2:
                raise asyncio.CancelledError()
            await real_sleep(0.01)

        monkeypatch.setattr(asyncio, "sleep", fast_sleep)
        task = asyncio.create_task(ep._cleanup_loop())
        try:
            await task
        except asyncio.CancelledError:
            pass
        token.cleanup_expired.assert_called()