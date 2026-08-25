"""MessageGateway 端到端集成测试。

覆盖 tasks.md 任务组 7 的 4 个场景：
  7.1 声明→就绪→发送命中 PLUGIN driver
  7.2 未就绪时回退 legacy
  7.3 napcat-adapter 真实声明
  7.4 现有插件兼容性
"""


import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.platform_io import DriverKind, RouteBinding, RouteKey, get_platform_io_manager
from src.plugin_runtime_v2.host.gateway_registrar import V2GatewayRegistrar
from src.plugin_runtime_v2.host.gateway_registry import GatewayRegistry
from src.plugin_runtime_v2.host.gateway_startup_summary import (
    GatewayStartupSummaryAdapter,
)
from src.plugin_runtime_v2.runner.plugin_loader import PluginLoader
from src.plugin_runtime_v2.sdk import Event, MaiBotPlugin, MessageGateway, Tool
from src.plugin_runtime_v2.sdk.decorators import MessageGatewayDeclaration
from src.plugin_runtime_v2.scope.approval_store import ScopeApprovalStore


# ── 测试用插件 ──────────────────────────────────────────────────


class GatewayPlugin(MaiBotPlugin):
    """带 @MessageGateway 声明的测试插件。"""

    plugin_id = "test.gateway"
    scopes = ["message:send:*"]

    @MessageGateway(
        name="test_gateway",
        platform="test_platform",
        protocol="test_protocol",
        supports_send=True,
        supports_receive=True,
        metadata={"tool_name": "test.send_text"},
    )
    async def test_message_gateway(self) -> None:
        pass

    @Tool(name="test.send_text", description="测试发送工具", parameters_schema={"type": "object"})
    async def send_text_tool(self, args):
        return {"ok": True}

    async def on_load(self) -> None:
        pass


class PlainPlugin(MaiBotPlugin):
    """不带 @MessageGateway 声明的测试插件（兼容性验证）。"""

    plugin_id = "test.plain"
    scopes = []

    @Tool(name="plain_tool", description="普通工具", parameters_schema={"type": "object"})
    async def plain_tool(self, args):
        return {"ok": True}

    @Event(name="plain_event", description="普通事件", event_schema={})
    async def plain_event_handler(self, data):
        pass

    async def on_load(self) -> None:
        pass


# ── 7.3 napcat-adapter 真实声明集成测试 ──────────────────────────


_PLUGIN_DIR = Path(__file__).resolve().parents[2] / "plugins" / "maibot-team.napcat-adapter"
_PKG = "plugins.maibot_team.napcat_adapter"


def _bootstrap_napcat_package() -> None:
    """注册 napcat-adapter 包到 sys.modules，让 Python 自然导入子模块。"""
    # 清除可能已被其他测试注册的空子模块，让 Python 重新自然导入
    for sub in ("", ".codecs", ".codecs.inbound", ".codecs.outbound", ".services"):
        full = _PKG + sub
        if full in sys.modules:
            del sys.modules[full]
    for parent in ("plugins", "plugins.maibot_team"):
        if parent not in sys.modules:
            mod = types.ModuleType(parent)
            mod.__path__ = []  # type: ignore[assignment]
            sys.modules[parent] = mod
    # 只注册父包，子包由 Python 自然导入
    mod = types.ModuleType(_PKG)
    mod.__path__ = [str(_PLUGIN_DIR)]  # type: ignore[assignment]
    sys.modules[_PKG] = mod


@pytest.mark.asyncio
async def test_napcat_gateway_declaration_loaded():
    """7.3: napcat-adapter 的 qq_gateway 声明被正确收集。"""
    _bootstrap_napcat_package()
    from plugins.maibot_team.napcat_adapter.plugin import NapCatAdapterPlugin

    loader = PluginLoader(NapCatAdapterPlugin)
    _, _, _, gateway_decls, _ = await loader.load()

    assert len(gateway_decls) == 1
    decl = gateway_decls[0]
    assert decl.name == "qq_gateway"
    assert decl.platform == "qq"
    assert decl.protocol == "onebot11"
    assert decl.supports_send is True
    assert decl.metadata.get("tool_name") == "napcat.send_text"


# ── 7.4 现有插件兼容性验证 ──────────────────────────────────────


@pytest.mark.asyncio
async def test_existing_plugins_unaffected():
    """7.4: 不声明 @MessageGateway 的插件 gateway_declarations 为空。"""
    loader = PluginLoader(PlainPlugin)
    tools, events, cards, gateway_decls, instance = await loader.load()

    assert gateway_decls == []
    assert len(tools) == 1
    assert tools[0]["name"] == "plain_tool"
    assert len(events) == 1
    assert events[0]["name"] == "plain_event"


@pytest.mark.asyncio
async def test_gateway_plugin_declarations_collected():
    """7.4 补充: 声明 @MessageGateway 的插件 gateway_declarations 正确收集。"""
    loader = PluginLoader(GatewayPlugin)
    tools, events, cards, gateway_decls, instance = await loader.load()

    assert len(gateway_decls) == 1
    assert gateway_decls[0].name == "test_gateway"
    assert gateway_decls[0].platform == "test_platform"
    assert len(tools) == 1


# ── 7.1 声明→就绪→发送命中 PLUGIN driver ────────────────────────


@pytest.mark.asyncio
async def test_e2e_send_hits_plugin_driver():
    """7.1: 声明→就绪→驱动注册→resolve_drivers 命中 PLUGIN driver。"""
    platform_io = get_platform_io_manager()

    gateway_registry = GatewayRegistry()
    scope_store = ScopeApprovalStore()
    # 直接设置 _approvals 绕过 ScopeVocabulary 验证（message:send:* 不在词汇表中）
    scope_store._approvals["test.gateway"] = {
        "granted_scopes": {"message:send:*"},
        "updated_at": 0,
        "updated_by": "test",
    }
    summary = GatewayStartupSummaryAdapter()
    registrar = V2GatewayRegistrar(
        gateway_registry=gateway_registry,
        scope_store=scope_store,
        startup_summary=summary,
    )

    decl = MessageGatewayDeclaration(
        name="test_gateway",
        platform="test_platform",
        protocol="test_protocol",
        supports_send=True,
        supports_receive=True,
        metadata={"tool_name": "test.send_text"},
    )
    gateway_registry.register_declarations("test.gateway", [decl])

    await registrar.on_gateway_ready(
        plugin_id="test.gateway",
        gateway_name="test_gateway",
        platform="test_platform",
        runner_listen_address="127.0.0.1:9999",
    )

    route_key = RouteKey(platform="test_platform")
    drivers = platform_io.resolve_drivers(route_key)
    plugin_drivers = [d for d in drivers if d.descriptor.kind == DriverKind.PLUGIN]
    assert len(plugin_drivers) > 0
    assert any("test.gateway" in d.driver_id for d in plugin_drivers)

    await registrar.on_gateway_not_ready("test.gateway", "test_gateway")


# ── 7.2 未就绪时回退 legacy ─────────────────────────────────────


@pytest.mark.asyncio
async def test_e2e_fallback_legacy_when_not_ready():
    """7.2: 声明但不上报 ready → resolve_drivers 不命中 PLUGIN driver。"""
    platform_io = get_platform_io_manager()

    gateway_registry = GatewayRegistry()
    gateway_registry.register_declarations("test.gateway", [
        MessageGatewayDeclaration(
            name="test_gateway",
            platform="test_platform_2",
            protocol="test_protocol",
            supports_send=True,
            supports_receive=True,
            metadata={"tool_name": "test.send_text"},
        )
    ])

    route_key = RouteKey(platform="test_platform_2")
    drivers = platform_io.resolve_drivers(route_key)
    plugin_drivers = [d for d in drivers if d.descriptor.kind == DriverKind.PLUGIN]
    assert len(plugin_drivers) == 0


# ── 启动摘要集成验证 ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_startup_summary_reports_gateway_status():
    """6.1 验收: 启动摘要含网关状态条目。"""
    gateway_registry = GatewayRegistry()
    scope_store = ScopeApprovalStore()
    summary = GatewayStartupSummaryAdapter()
    registrar = V2GatewayRegistrar(
        gateway_registry=gateway_registry,
        scope_store=scope_store,
        startup_summary=summary,
    )

    decl = MessageGatewayDeclaration(
        name="summary_test_gateway",
        platform="summary_platform",
        protocol="test",
        supports_send=True,
        supports_receive=False,
        metadata={"tool_name": "test.send"},
    )
    gateway_registry.register_declarations("test.summary", [decl])

    await registrar.on_gateway_ready(
        plugin_id="test.summary",
        gateway_name="summary_test_gateway",
        platform="summary_platform",
        runner_listen_address="127.0.0.1:9999",
    )

    assert summary.get_entry_count() >= 1
    formatted = summary.format_summary()
    assert "test.summary/summary_test_gateway" in formatted
    assert "已注册并绑定" in formatted

    await registrar.on_gateway_not_ready("test.summary", "summary_test_gateway")