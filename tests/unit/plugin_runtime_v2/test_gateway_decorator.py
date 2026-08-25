"""@MessageGateway 装饰器单元测试。

覆盖测试接缝 1（装饰器声明附着）和测试接缝 2（PluginLoader 扫描）。
纯单元测试，不依赖 gRPC/Platform IO/Runner。
"""

from dataclasses import FrozenInstanceError

import pytest

from src.plugin_runtime_v2.sdk import MessageGateway, MessageGatewayDeclaration


class TestMessageGatewayDeclaration:
    """1.1 MessageGatewayDeclaration 数据模型测试。"""

    def test_basic_construction(self):
        d = MessageGatewayDeclaration(name="g", platform="qq", protocol="onebot11")
        assert d.name == "g"
        assert d.platform == "qq"
        assert d.protocol == "onebot11"
        assert d.supports_send is True
        assert d.supports_receive is False
        assert d.route_type == ""
        assert d.metadata == {}

    def test_frozen(self):
        d = MessageGatewayDeclaration(name="g", platform="qq", protocol="onebot11")
        with pytest.raises(FrozenInstanceError):
            d.name = "other"

    def test_metadata_default_not_shared(self):
        d1 = MessageGatewayDeclaration(name="g1", platform="qq", protocol="onebot11")
        d2 = MessageGatewayDeclaration(name="g2", platform="qq", protocol="onebot11")
        d1.metadata["key"] = "value"
        assert d2.metadata == {}

    def test_custom_fields(self):
        d = MessageGatewayDeclaration(
            name="g",
            platform="qq",
            protocol="onebot11",
            supports_send=False,
            supports_receive=True,
            route_type="private",
            metadata={"tool": "send_text"},
        )
        assert d.supports_send is False
        assert d.supports_receive is True
        assert d.route_type == "private"
        assert d.metadata == {"tool": "send_text"}


class TestMessageGatewayDecorator:
    """1.2 @MessageGateway 装饰器测试。"""

    def test_decorator_attaches_declaration(self):
        @MessageGateway(name="qq_gateway", platform="qq", protocol="onebot11")
        async def gateway(self):
            pass

        assert hasattr(gateway, "_message_gateway")
        decl = gateway._message_gateway
        assert isinstance(decl, MessageGatewayDeclaration)
        assert decl.name == "qq_gateway"
        assert decl.platform == "qq"
        assert decl.protocol == "onebot11"
        assert decl.supports_send is True
        assert decl.supports_receive is False

    def test_decorator_with_all_fields(self):
        @MessageGateway(
            name="g",
            platform="qq",
            protocol="onebot11",
            supports_send=False,
            supports_receive=True,
            route_type="group",
            metadata={"tool": "send_text"},
        )
        async def gateway(self):
            pass

        decl = gateway._message_gateway
        assert decl.supports_send is False
        assert decl.supports_receive is True
        assert decl.route_type == "group"
        assert decl.metadata == {"tool": "send_text"}

    def test_empty_name_raises(self):
        with pytest.raises(ValueError, match="name"):

            @MessageGateway(name="", platform="qq", protocol="onebot11")
            async def gateway(self):
                pass

    def test_empty_platform_raises(self):
        with pytest.raises(ValueError, match="platform"):

            @MessageGateway(name="g", platform="", protocol="onebot11")
            async def gateway(self):
                pass

    def test_missing_required_args_raises(self):
        with pytest.raises(TypeError):
            MessageGateway(platform="qq", protocol="onebot11")

    def test_metadata_none_becomes_empty_dict(self):
        @MessageGateway(name="g", platform="qq", protocol="onebot11", metadata=None)
        async def gateway(self):
            pass

        assert gateway._message_gateway.metadata == {}

    def test_decorator_preserves_method_behavior(self):
        @MessageGateway(name="g", platform="qq", protocol="onebot11")
        async def gateway(self):
            return "original"

        import asyncio

        result = asyncio.run(gateway(None))
        assert result == "original"

    def test_not_marked_as_tool_or_event(self):
        @MessageGateway(name="g", platform="qq", protocol="onebot11")
        async def gateway(self):
            pass

        assert not hasattr(gateway, "_mcp_tool")
        assert not hasattr(gateway, "_mcp_event")


class TestGatewayDeclarationImport:
    """1.3 SDK __init__.py 导出测试。"""

    def test_importable_from_sdk(self):
        from src.plugin_runtime_v2.sdk import MessageGateway as MG
        from src.plugin_runtime_v2.sdk import MessageGatewayDeclaration as MGD

        assert MG is not None
        assert MGD is not None

    def test_existing_exports_unaffected(self):
        from src.plugin_runtime_v2.sdk import Command, Event, HomeCard, Tool

        assert Tool is not None
        assert Event is not None
        assert Command is not None
        assert HomeCard is not None


# ── 3.5: Runner 侧扫描与上报单元测试 ────────────────────────────


class TestPluginLoaderGatewayScan:
    """3.1/3.2 PluginLoader 扫描 @MessageGateway 声明。"""

    @pytest.fixture
    def plugin_cls_with_gateway(self):
        from src.plugin_runtime_v2.sdk import Event, MessageGateway, Tool
        from src.plugin_runtime_v2.sdk.plugin import MaiBotPlugin

        class _PluginWithGateway(MaiBotPlugin):
            plugin_id = "test.gateway_plugin"

            @Tool(name="send_text", description="发送文本")
            async def send_text(self, args: dict) -> dict:
                return {"ok": True}

            @Event(name="on_message", description="消息事件")
            async def on_message(self, args: dict) -> None:
                pass

            @MessageGateway(name="qq_gw", platform="qq", protocol="onebot11")
            async def qq_gateway(self):
                pass

        return _PluginWithGateway

    @pytest.fixture
    def plugin_cls_without_gateway(self):
        from src.plugin_runtime_v2.sdk import Tool
        from src.plugin_runtime_v2.sdk.plugin import MaiBotPlugin

        class _PluginNoGateway(MaiBotPlugin):
            plugin_id = "test.no_gateway"

            @Tool(name="hello", description="打招呼")
            async def hello(self, args: dict) -> dict:
                return {"ok": True}

        return _PluginNoGateway

    def test_gateway_collected(self, plugin_cls_with_gateway):
        from src.plugin_runtime_v2.runner.plugin_loader import PluginLoader

        loader = PluginLoader(plugin_cls_with_gateway)
        import asyncio
        tools, events, homecards, gateways, instance = asyncio.run(loader.load())
        assert len(gateways) == 1
        assert gateways[0].name == "qq_gw"
        assert gateways[0].platform == "qq"
        assert gateways[0].protocol == "onebot11"

    def test_no_gateway_empty_list(self, plugin_cls_without_gateway):
        from src.plugin_runtime_v2.runner.plugin_loader import PluginLoader

        loader = PluginLoader(plugin_cls_without_gateway)
        import asyncio
        tools, events, homecards, gateways, instance = asyncio.run(loader.load())
        assert gateways == []

    def test_mixed_declarations_independent(self, plugin_cls_with_gateway):
        from src.plugin_runtime_v2.runner.plugin_loader import PluginLoader

        loader = PluginLoader(plugin_cls_with_gateway)
        import asyncio
        tools, events, homecards, gateways, instance = asyncio.run(loader.load())
        assert len(tools) == 1
        assert tools[0]["name"] == "send_text"
        assert len(events) == 1
        assert events[0]["name"] == "on_message"
        assert len(gateways) == 1
        assert gateways[0].name == "qq_gw"

    def test_load_return_has_gateway_field(self, plugin_cls_with_gateway):
        from src.plugin_runtime_v2.runner.plugin_loader import PluginLoader

        loader = PluginLoader(plugin_cls_with_gateway)
        import asyncio
        result = asyncio.run(loader.load())
        assert len(result) == 5
        tools, events, homecards, gateways, instance = result
        assert instance is not None
        assert len(gateways) == 1


class TestRunnerEndpointReportReady:
    """3.3 RunnerEndpoint.report_gateway_ready 测试。"""

    def test_report_gateway_ready_sends_payload(self):
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, PropertyMock

        from src.plugin_runtime_v2.host.connection import ConnectionState
        from src.plugin_runtime_v2.runner.endpoint import RunnerEndpoint
        from src.plugin_runtime_v2.proto import common_pb2

        endpoint = RunnerEndpoint.__new__(RunnerEndpoint)
        endpoint._state = ConnectionState.READY
        endpoint._stream_call = MagicMock()
        endpoint._stream_call.write = AsyncMock()
        endpoint._config = MagicMock()
        endpoint._config.runner_id = "test-runner"

        asyncio.run(endpoint.report_gateway_ready(
            gateway_name="qq_gw",
            platform="qq",
            ready=True,
            account_id="12345",
            scope="message:send:qq",
        ))

        endpoint._stream_call.write.assert_called_once()
        msg = endpoint._stream_call.write.call_args[0][0]
        assert msg.WhichOneof("payload") == "gateway_ready"
        assert msg.gateway_ready.gateway_name == "qq_gw"
        assert msg.gateway_ready.platform == "qq"
        assert msg.gateway_ready.ready is True
        assert msg.gateway_ready.account_id == "12345"
        assert msg.gateway_ready.scope == "message:send:qq"

    def test_report_gateway_not_ready(self):
        import asyncio
        from unittest.mock import AsyncMock, MagicMock

        from src.plugin_runtime_v2.host.connection import ConnectionState
        from src.plugin_runtime_v2.runner.endpoint import RunnerEndpoint

        endpoint = RunnerEndpoint.__new__(RunnerEndpoint)
        endpoint._state = ConnectionState.READY
        endpoint._stream_call = MagicMock()
        endpoint._stream_call.write = AsyncMock()
        endpoint._config = MagicMock()
        endpoint._config.runner_id = "test-runner"

        asyncio.run(endpoint.report_gateway_ready(
            gateway_name="qq_gw",
            platform="qq",
            ready=False,
        ))

        msg = endpoint._stream_call.write.call_args[0][0]
        assert msg.gateway_ready.ready is False

    def test_report_gateway_ready_not_connected_raises(self):
        import asyncio
        from unittest.mock import MagicMock

        from src.plugin_runtime_v2.host.connection import ConnectionState
        from src.plugin_runtime_v2.runner.endpoint import RunnerEndpoint

        endpoint = RunnerEndpoint.__new__(RunnerEndpoint)
        endpoint._state = ConnectionState.DISCONNECTED
        endpoint._stream_call = None
        endpoint._config = MagicMock()
        endpoint._config.runner_id = "test-runner"

        with pytest.raises(ConnectionError):
            asyncio.run(endpoint.report_gateway_ready(
                gateway_name="qq_gw",
                platform="qq",
            ))


class TestPluginContextReportReady:
    """3.4 PluginContext.report_gateway_ready/not_ready 测试。"""

    @pytest.fixture
    def ctx_with_gateway(self):
        from unittest.mock import AsyncMock, MagicMock

        from src.plugin_runtime_v2.sdk.context import PluginContext
        from src.plugin_runtime_v2.sdk.decorators import MessageGatewayDeclaration

        runner = MagicMock()
        runner.report_gateway_ready = AsyncMock()
        runner.is_ready = True

        gateway_decls = [
            MessageGatewayDeclaration(name="qq_gw", platform="qq", protocol="onebot11"),
        ]

        ctx = PluginContext(
            plugin_id="test",
            granted_scopes={"message:send:qq"},
            runner_endpoint=runner,
            homecard_registry={},
            gateway_declarations=gateway_decls,
        )
        return ctx, runner

    def test_report_gateway_ready_delegates(self, ctx_with_gateway):
        import asyncio

        ctx, runner = ctx_with_gateway
        asyncio.run(ctx.report_gateway_ready("qq_gw"))

        runner.report_gateway_ready.assert_called_once_with(
            gateway_name="qq_gw",
            platform="qq",
            ready=True,
        )

    def test_report_gateway_not_ready_delegates(self, ctx_with_gateway):
        import asyncio

        ctx, runner = ctx_with_gateway
        asyncio.run(ctx.report_gateway_not_ready("qq_gw"))

        runner.report_gateway_ready.assert_called_once_with(
            gateway_name="qq_gw",
            platform="qq",
            ready=False,
        )

    def test_unknown_gateway_name_logs_warning(self, ctx_with_gateway):
        import asyncio

        ctx, runner = ctx_with_gateway
        asyncio.run(ctx.report_gateway_ready("unknown_gw"))

        runner.report_gateway_ready.assert_not_called()