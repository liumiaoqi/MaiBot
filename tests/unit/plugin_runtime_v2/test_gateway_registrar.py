"""V2GatewayRegistrar 单元测试。

覆盖测试接缝 3（scope gating）和测试接缝 4（先注销后注册）。
用 mock scope_store、mock Platform IO Manager、mock startup_summary。
"""


import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.plugin_runtime_v2.host.gateway_registrar import V2GatewayRegistrar
from src.plugin_runtime_v2.host.gateway_registry import GatewayRegistry
from src.plugin_runtime_v2.sdk.decorators import MessageGatewayDeclaration


def _make_mock_platform_io():
    """创建 mock Platform IO Manager。"""
    mgr = MagicMock()
    mgr.is_started = True
    mgr.add_driver = AsyncMock()
    mgr.register_driver = MagicMock()
    mgr.remove_driver = AsyncMock()
    mgr.unregister_driver = MagicMock()
    mgr.bind_send_route = MagicMock()
    mgr.bind_receive_route = MagicMock()
    mgr.send_route_table = MagicMock()
    mgr.send_route_table.remove_bindings_by_driver = MagicMock()
    mgr.receive_route_table = MagicMock()
    mgr.receive_route_table.remove_bindings_by_driver = MagicMock()
    return mgr


def _make_mock_scope_store(granted_scopes: set[str]):
    """创建 mock ScopeStore。"""
    store = MagicMock()
    store.get_granted_scopes = MagicMock(return_value=granted_scopes)
    return store


def _make_mock_startup_summary():
    """创建 mock startup_summary。"""
    summary = MagicMock()
    summary.report_gateway_status = MagicMock()
    return summary


def _make_gateway_decl(**kwargs):
    """创建 MessageGatewayDeclaration。"""
    defaults = {
        "name": "qq_gw",
        "platform": "qq",
        "protocol": "onebot11",
        "supports_send": True,
        "supports_receive": False,
        "route_type": "",
        "metadata": {"tool_name": "napcat.send_text"},
    }
    defaults.update(kwargs)
    return MessageGatewayDeclaration(**defaults)


class TestGatewayRegistry:
    """4.1 GatewayRegistry 基本测试。"""

    def test_register_and_get(self):
        reg = GatewayRegistry()
        decls = [_make_gateway_decl()]
        reg.register_declarations("plugin_a", decls)
        assert reg.get_declaration("plugin_a", "qq_gw") is not None
        assert len(reg.get_all_declarations("plugin_a")) == 1

    def test_duplicate_name_raises(self):
        reg = GatewayRegistry()
        decls = [
            _make_gateway_decl(name="same"),
            _make_gateway_decl(name="same"),
        ]
        with pytest.raises(ValueError, match="重复"):
            reg.register_declarations("plugin_a", decls)

    def test_remove(self):
        reg = GatewayRegistry()
        reg.register_declarations("plugin_a", [_make_gateway_decl()])
        reg.remove("plugin_a")
        assert reg.get_declaration("plugin_a", "qq_gw") is None
        assert reg.get_all_declarations("plugin_a") == []

    def test_get_nonexistent(self):
        reg = GatewayRegistry()
        assert reg.get_declaration("no_plugin", "no_gw") is None
        assert reg.get_all_declarations("no_plugin") == []


class TestV2GatewayRegistrar:
    """4.8 V2GatewayRegistrar scope gating + 先注销后注册测试。"""

    @pytest.fixture
    def setup(self):
        """创建 registrar + mock 依赖。"""
        registry = GatewayRegistry()
        scope_store = _make_mock_scope_store({"message:send:qq"})
        summary = _make_mock_startup_summary()
        registrar = V2GatewayRegistrar(
            gateway_registry=registry,
            scope_store=scope_store,
            startup_summary=summary,
        )
        return registrar, registry, scope_store, summary

    @pytest.mark.asyncio
    async def test_scope_granted_binds_send(self, setup):
        """scope 授予时 send+receive 都绑定。"""
        registrar, registry, _, _ = setup
        registry.register_declarations("p1", [_make_gateway_decl(supports_receive=True)])
        mock_pio = _make_mock_platform_io()

        with patch("src.plugin_runtime_v2.host.gateway_registrar.get_platform_io_manager", return_value=mock_pio):
            await registrar.on_gateway_ready(
                plugin_id="p1", gateway_name="qq_gw",
                platform="qq", runner_listen_address="127.0.0.1:50051",
            )

        mock_pio.add_driver.assert_called_once()
        mock_pio.bind_send_route.assert_called_once()
        mock_pio.bind_receive_route.assert_called_once()

    @pytest.mark.asyncio
    async def test_scope_denied_no_send_bind(self, setup):
        """scope 未授予 message:send:* 时只绑 receive 不绑 send。"""
        registrar, registry, scope_store, summary = setup
        scope_store.get_granted_scopes = MagicMock(return_value=set())
        registry.register_declarations("p1", [_make_gateway_decl(supports_receive=True)])
        mock_pio = _make_mock_platform_io()

        with patch("src.plugin_runtime_v2.host.gateway_registrar.get_platform_io_manager", return_value=mock_pio):
            await registrar.on_gateway_ready(
                plugin_id="p1", gateway_name="qq_gw",
                platform="qq", runner_listen_address="127.0.0.1:50051",
            )

        mock_pio.add_driver.assert_called_once()
        mock_pio.bind_send_route.assert_not_called()
        mock_pio.bind_receive_route.assert_called_once()
        summary.report_gateway_status.assert_any_call(
            plugin_id="p1", gateway_name="qq_gw",
            status="scope_denied",
            detail="message:send:qq 未授予",
        )

    @pytest.mark.asyncio
    async def test_declaration_not_found(self, setup):
        """声明不存在时 logger.warning + 启动摘要标记失败。"""
        registrar, _, _, summary = setup
        mock_pio = _make_mock_platform_io()

        with patch("src.plugin_runtime_v2.host.gateway_registrar.get_platform_io_manager", return_value=mock_pio):
            await registrar.on_gateway_ready(
                plugin_id="unknown", gateway_name="no_gw",
                platform="qq", runner_listen_address="127.0.0.1:50051",
            )

        mock_pio.add_driver.assert_not_called()
        summary.report_gateway_status.assert_called_with(
            plugin_id="unknown", gateway_name="no_gw",
            status="failed", detail="声明不存在",
        )

    @pytest.mark.asyncio
    async def test_reconnect_unregisters_old_first(self, setup):
        """连续两次 on_gateway_ready（断线重连）：第二次先注销旧驱动。"""
        registrar, registry, _, _ = setup
        registry.register_declarations("p1", [_make_gateway_decl()])
        mock_pio = _make_mock_platform_io()

        with patch("src.plugin_runtime_v2.host.gateway_registrar.get_platform_io_manager", return_value=mock_pio):
            await registrar.on_gateway_ready(
                plugin_id="p1", gateway_name="qq_gw",
                platform="qq", runner_listen_address="127.0.0.1:50051",
            )
            # 第二次（重连）
            await registrar.on_gateway_ready(
                plugin_id="p1", gateway_name="qq_gw",
                platform="qq", runner_listen_address="127.0.0.1:50051",
            )

        # remove_driver 至少调用一次（注销旧驱动）
        assert mock_pio.remove_driver.call_count >= 1
        # add_driver 调用两次（两次注册）
        assert mock_pio.add_driver.call_count == 2
        # send_route_table.remove_bindings_by_driver 至少调用一次（注销旧绑定）
        assert mock_pio.send_route_table.remove_bindings_by_driver.call_count >= 1

    @pytest.mark.asyncio
    async def test_registration_failure_reports(self, setup):
        """驱动注册失败时双通道上报 + 启动摘要标记失败。"""
        registrar, registry, _, summary = setup
        registry.register_declarations("p1", [_make_gateway_decl()])
        mock_pio = _make_mock_platform_io()
        mock_pio.add_driver = AsyncMock(side_effect=RuntimeError("PIO 注册失败"))

        with patch("src.plugin_runtime_v2.host.gateway_registrar.get_platform_io_manager", return_value=mock_pio):
            await registrar.on_gateway_ready(
                plugin_id="p1", gateway_name="qq_gw",
                platform="qq", runner_listen_address="127.0.0.1:50051",
            )

        # 启动摘要标记失败
        status_calls = [c for c in summary.report_gateway_status.call_args_list
                        if c.kwargs.get("status") == "failed"]
        assert len(status_calls) >= 1

    @pytest.mark.asyncio
    async def test_on_gateway_not_ready_idempotent(self, setup):
        """on_gateway_not_ready 幂等（不存在时不报错）。"""
        registrar, _, _, _ = setup
        mock_pio = _make_mock_platform_io()

        with patch("src.plugin_runtime_v2.host.gateway_registrar.get_platform_io_manager", return_value=mock_pio):
            # 不存在的网关，不报错
            await registrar.on_gateway_not_ready("p1", "nonexistent_gw")

        # remove_bindings_by_driver 仍被调用（幂等清理）
        mock_pio.send_route_table.remove_bindings_by_driver.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_runner_disconnected_unregisters_all(self, setup):
        """on_runner_disconnected 注销该插件所有网关。"""
        registrar, registry, _, _ = setup
        registry.register_declarations("p1", [
            _make_gateway_decl(name="gw1"),
            _make_gateway_decl(name="gw2"),
        ])
        mock_pio = _make_mock_platform_io()

        with patch("src.plugin_runtime_v2.host.gateway_registrar.get_platform_io_manager", return_value=mock_pio):
            # 先注册两个网关
            await registrar.on_gateway_ready(
                plugin_id="p1", gateway_name="gw1",
                platform="qq", runner_listen_address="127.0.0.1:50051",
            )
            await registrar.on_gateway_ready(
                plugin_id="p1", gateway_name="gw2",
                platform="qq", runner_listen_address="127.0.0.1:50051",
            )
            # 断开
            await registrar.on_runner_disconnected("p1")

        # 两个网关的绑定都被移除
        assert mock_pio.send_route_table.remove_bindings_by_driver.call_count >= 2
        assert mock_pio.receive_route_table.remove_bindings_by_driver.call_count >= 2