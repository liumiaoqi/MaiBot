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
        """创建 registrar + mock 依赖。

        ⚠️ 授予的 scope 是 ``message:send:text``（**词汇表里的真 scope**）。
        原夹具写的是 ``message:send:qq``——那是**平台名**，而 ``message:send:`` 之后按
        词汇表（``scope/vocabulary.py``）跟的是**消息类型**；这个词在全仓词汇表里不存在。
        夹具用了不存在的 scope，等于把 bug 的约定固化成了"期望值"，真机上是
        "已授予 message:send:text 却被判成不能发"（2026-10-16 修）。
        """
        registry = GatewayRegistry()
        scope_store = _make_mock_scope_store({"message:send:text"})
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
        """**反向判据①**：一个 send scope 都没有 ⇒ 只绑 receive、不绑 send，且出警告。"""
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
            detail="未授予任何 message:send:*（发送资格）",
            platform="qq",
        )

    @pytest.mark.asyncio
    async def test_granted_message_type_scope_enables_send(self, setup):
        """**修复的正向判据**：只授予 ``message:send:text``（真机现场就是这样）⇒ send 生效。

        这正是"能听不能说"的那个洞：修前按 ``message:send:{platform}`` 找，永远匹配不上。
        """
        registrar, registry, _, summary = setup
        registry.register_declarations("p1", [_make_gateway_decl(supports_receive=True)])
        mock_pio = _make_mock_platform_io()

        with patch("src.plugin_runtime_v2.host.gateway_registrar.get_platform_io_manager", return_value=mock_pio):
            await registrar.on_gateway_ready(
                plugin_id="p1", gateway_name="qq_gw",
                platform="qq", runner_listen_address="127.0.0.1:50051",
            )

        mock_pio.bind_send_route.assert_called_once()
        mock_pio.bind_receive_route.assert_called_once()
        detail = next(
            call.kwargs["detail"] for call in summary.report_gateway_status.call_args_list
            if call.kwargs.get("status") == "registered"
        )
        assert "send=True" in detail, f"注册摘要里 send 仍为假：{detail}"

    @pytest.mark.asyncio
    async def test_only_forward_scope_still_registers_send(self, setup):
        """**反向判据②**：只授予 ``message:send:forward`` ⇒ 注册期**放行**（语义写在这里）。

        为什么放行：网关注册时**只知道平台**、不知道将来要发哪种消息；把"某一种类型"当成
        "整体能不能发"的判据，就会把只授了 forward 的插件判成不能发（同一个 bug 换张脸）。
        **类型粒度在发送那一刻生效**：``host/servicer.py:709-718`` 把 TEXT→``message:send:text``
        并返回 ``SCOPE_DENIED`` ⇒ 该插件**能注册、发 text 会被拒**。
        （发送侧那条判据不在本文件覆盖范围内，它有自己的用例；这里只钉注册期的分工。）
        """
        registrar, registry, scope_store, _ = setup
        scope_store.get_granted_scopes = MagicMock(return_value={"message:send:forward"})
        registry.register_declarations("p1", [_make_gateway_decl()])
        mock_pio = _make_mock_platform_io()

        with patch("src.plugin_runtime_v2.host.gateway_registrar.get_platform_io_manager", return_value=mock_pio):
            await registrar.on_gateway_ready(
                plugin_id="p1", gateway_name="qq_gw",
                platform="qq", runner_listen_address="127.0.0.1:50051",
            )

        mock_pio.bind_send_route.assert_called_once()

    @pytest.mark.asyncio
    async def test_wildcard_scope_enables_send(self, setup):
        """``message:send:*`` 通配 ⇒ 放行（e2e 夹具用的就是它，别把它判死）。"""
        registrar, registry, scope_store, _ = setup
        scope_store.get_granted_scopes = MagicMock(return_value={"message:send:*"})
        registry.register_declarations("p1", [_make_gateway_decl()])
        mock_pio = _make_mock_platform_io()

        with patch("src.plugin_runtime_v2.host.gateway_registrar.get_platform_io_manager", return_value=mock_pio):
            await registrar.on_gateway_ready(
                plugin_id="p1", gateway_name="qq_gw",
                platform="qq", runner_listen_address="127.0.0.1:50051",
            )

        mock_pio.bind_send_route.assert_called_once()

    @pytest.mark.asyncio
    async def test_receive_only_scope_does_not_grant_send(self, setup):
        """**反向判据③（红线）**：只有 ``message:receive:*`` ⇒ 仍然拒；声明不替代授权。

        防的是"把判据改成'只要声明了 supports_send 就放行'"——那等于把权限检查删掉。
        """
        registrar, registry, scope_store, summary = setup
        scope_store.get_granted_scopes = MagicMock(
            return_value={"message:receive:group", "message:receive:private", "message:receive:notice"}
        )
        registry.register_declarations("p1", [_make_gateway_decl(supports_send=True)])
        mock_pio = _make_mock_platform_io()

        with patch("src.plugin_runtime_v2.host.gateway_registrar.get_platform_io_manager", return_value=mock_pio):
            await registrar.on_gateway_ready(
                plugin_id="p1", gateway_name="qq_gw",
                platform="qq", runner_listen_address="127.0.0.1:50051",
            )

        mock_pio.bind_send_route.assert_not_called()
        denied = [
            call.kwargs for call in summary.report_gateway_status.call_args_list
            if call.kwargs.get("status") == "scope_denied"
        ]
        assert denied, "只授 receive 却放行了 send（红线③：授权不得被声明替代）"

    @pytest.mark.asyncio
    async def test_summary_carries_platform_not_placeholder(self, setup):
        """**可观测性判据**：启动摘要必须拿到 ``platform``（否则渲染成 ``platform=?``）。

        修前 ``_report_summary`` 不传 platform，摘要适配器的默认空值被渲染成 ``?``
        （``gateway_startup_summary.py:39/54``）——真机上那条 ``platform=?`` 就是这么来的，
        它反过来把排障引向"平台没解析"这个错误方向。
        """
        registrar, registry, _, summary = setup
        registry.register_declarations("p1", [_make_gateway_decl()])
        mock_pio = _make_mock_platform_io()

        with patch("src.plugin_runtime_v2.host.gateway_registrar.get_platform_io_manager", return_value=mock_pio):
            await registrar.on_gateway_ready(
                plugin_id="p1", gateway_name="qq_gw",
                platform="qq", runner_listen_address="127.0.0.1:50051",
            )

        for call in summary.report_gateway_status.call_args_list:
            assert call.kwargs.get("platform") == "qq", f"摘要没拿到平台：{call.kwargs}"

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
        # ⚠️ 2026-10-16：断言补上 `platform="qq"`——修前 `_report_summary` 不传平台，
        # 摘要把空值渲染成 `platform=?`（真机现场）。判据本身没变：仍然要求"标记失败 + 原因"。
        summary.report_gateway_status.assert_called_with(
            plugin_id="unknown", gateway_name="no_gw",
            status="failed", detail="声明不存在", platform="qq",
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