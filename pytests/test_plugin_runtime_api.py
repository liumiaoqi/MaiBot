"""插件 API 注册与调用测试。"""

from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

from src.plugin_runtime.integration import PluginRuntimeManager
from src.plugin_runtime.host.supervisor import PluginSupervisor
from src.plugin_runtime.protocol.envelope import (
    ComponentDeclaration,
    Envelope,
    MessageType,
    RegisterPluginPayload,
    UnregisterPluginPayload,
)


def _build_manager(*supervisors: PluginSupervisor) -> PluginRuntimeManager:
    """构造一个最小可用的插件运行时管理器。

    Args:
        *supervisors: 需要挂载的监督器列表。

    Returns:
        PluginRuntimeManager: 已注入监督器的运行时管理器。
    """

    manager = PluginRuntimeManager()
    if supervisors:
        manager._builtin_supervisor = supervisors[0]
    if len(supervisors) > 1:
        manager._third_party_supervisor = supervisors[1]
    return manager


async def _register_plugin(
    supervisor: PluginSupervisor,
    plugin_id: str,
    components: List[Dict[str, Any]],
) -> Envelope:
    """通过 Supervisor 注册测试插件。

    Args:
        supervisor: 目标监督器。
        plugin_id: 测试插件 ID。
        components: 组件声明列表。

    Returns:
        Envelope: 注册响应信封。
    """

    payload = RegisterPluginPayload(
        plugin_id=plugin_id,
        plugin_version="1.0.0",
        components=[
            ComponentDeclaration(
                name=str(component.get("name", "") or ""),
                component_type=str(component.get("component_type", "") or ""),
                plugin_id=plugin_id,
                metadata=component.get("metadata", {}) if isinstance(component.get("metadata"), dict) else {},
            )
            for component in components
        ],
    )
    return await supervisor._handle_register_plugin(
        Envelope(
            request_id=1,
            message_type=MessageType.REQUEST,
            method="plugin.register_components",
            plugin_id=plugin_id,
            payload=payload.model_dump(),
        )
    )


async def _unregister_plugin(supervisor: PluginSupervisor, plugin_id: str) -> Envelope:
    """通过 Supervisor 注销测试插件。

    Args:
        supervisor: 目标监督器。
        plugin_id: 测试插件 ID。

    Returns:
        Envelope: 注销响应信封。
    """

    payload = UnregisterPluginPayload(plugin_id=plugin_id, reason="test")
    return await supervisor._handle_unregister_plugin(
        Envelope(
            request_id=2,
            message_type=MessageType.REQUEST,
            method="plugin.unregister",
            plugin_id=plugin_id,
            payload=payload.model_dump(),
        )
    )


@pytest.mark.asyncio
async def test_register_plugin_syncs_dedicated_api_registry() -> None:
    """插件注册时应将 API 同步到独立注册表，而不是通用组件表。"""

    supervisor = PluginSupervisor(plugin_dirs=[])
    response = await _register_plugin(
        supervisor,
        "provider",
        [
            {
                "name": "render_html",
                "component_type": "API",
                "metadata": {
                    "description": "渲染 HTML",
                    "version": "1",
                    "public": True,
                },
            }
        ],
    )

    assert response.payload["accepted"] is True
    assert response.payload["registered_components"] == 0
    assert response.payload["registered_apis"] == 1
    assert supervisor.api_registry.get_api("provider", "render_html") is not None
    assert supervisor.component_registry.get_component("provider.render_html") is None

    unregister_response = await _unregister_plugin(supervisor, "provider")
    assert unregister_response.payload["removed_apis"] == 1
    assert supervisor.api_registry.get_api("provider", "render_html") is None


@pytest.mark.asyncio
async def test_api_call_allows_public_api_between_plugins(monkeypatch: pytest.MonkeyPatch) -> None:
    """公开 API 应允许其他插件通过 Host 转发调用。"""

    provider_supervisor = PluginSupervisor(plugin_dirs=[])
    consumer_supervisor = PluginSupervisor(plugin_dirs=[])
    await _register_plugin(
        provider_supervisor,
        "provider",
        [
            {
                "name": "render_html",
                "component_type": "API",
                "metadata": {
                    "description": "渲染 HTML",
                    "version": "1",
                    "public": True,
                },
            }
        ],
    )
    await _register_plugin(consumer_supervisor, "consumer", [])

    captured: Dict[str, Any] = {}

    async def fake_invoke_api(
        plugin_id: str,
        component_name: str,
        args: Dict[str, Any] | None = None,
        timeout_ms: int = 30000,
    ) -> Any:
        """模拟 API RPC 调用。"""

        captured["plugin_id"] = plugin_id
        captured["component_name"] = component_name
        captured["args"] = args or {}
        captured["timeout_ms"] = timeout_ms
        return SimpleNamespace(error=None, payload={"success": True, "result": {"image": "ok"}})

    monkeypatch.setattr(provider_supervisor, "invoke_api", fake_invoke_api)

    manager = _build_manager(provider_supervisor, consumer_supervisor)
    result = await manager._cap_api_call(
        "consumer",
        "api.call",
        {
            "api_name": "provider.render_html",
            "version": "1",
            "args": {"html": "<div>Hello</div>"},
        },
    )

    assert result == {"success": True, "result": {"image": "ok"}}
    assert captured["plugin_id"] == "provider"
    assert captured["component_name"] == "render_html"
    assert captured["args"] == {"html": "<div>Hello</div>"}


@pytest.mark.asyncio
async def test_api_call_rejects_private_api_between_plugins() -> None:
    """未公开的 API 默认不允许跨插件调用。"""

    provider_supervisor = PluginSupervisor(plugin_dirs=[])
    consumer_supervisor = PluginSupervisor(plugin_dirs=[])
    await _register_plugin(
        provider_supervisor,
        "provider",
        [
            {
                "name": "secret_api",
                "component_type": "API",
                "metadata": {
                    "description": "私有 API",
                    "version": "1",
                    "public": False,
                },
            }
        ],
    )
    await _register_plugin(consumer_supervisor, "consumer", [])

    manager = _build_manager(provider_supervisor, consumer_supervisor)
    result = await manager._cap_api_call(
        "consumer",
        "api.call",
        {
            "api_name": "provider.secret_api",
            "args": {},
        },
    )

    assert result["success"] is False
    assert "未公开" in str(result["error"])


@pytest.mark.asyncio
async def test_api_list_and_component_toggle_use_dedicated_registry() -> None:
    """API 列表与组件启停应直接作用于独立 API 注册表。"""

    provider_supervisor = PluginSupervisor(plugin_dirs=[])
    consumer_supervisor = PluginSupervisor(plugin_dirs=[])
    await _register_plugin(
        provider_supervisor,
        "provider",
        [
            {
                "name": "public_api",
                "component_type": "API",
                "metadata": {"version": "1", "public": True},
            },
            {
                "name": "private_api",
                "component_type": "API",
                "metadata": {"version": "1", "public": False},
            },
        ],
    )
    await _register_plugin(
        consumer_supervisor,
        "consumer",
        [
            {
                "name": "self_private_api",
                "component_type": "API",
                "metadata": {"version": "1", "public": False},
            }
        ],
    )

    manager = _build_manager(provider_supervisor, consumer_supervisor)
    list_result = await manager._cap_api_list("consumer", "api.list", {})

    assert list_result["success"] is True
    api_names = {(item["plugin_id"], item["name"]) for item in list_result["apis"]}
    assert ("provider", "public_api") in api_names
    assert ("provider", "private_api") not in api_names
    assert ("consumer", "self_private_api") in api_names

    disable_result = await manager._cap_component_disable(
        "consumer",
        "component.disable",
        {
            "name": "provider.public_api",
            "component_type": "API",
            "scope": "global",
            "stream_id": "",
        },
    )
    assert disable_result["success"] is True
    assert provider_supervisor.api_registry.get_api("provider", "public_api", enabled_only=True) is None

    enable_result = await manager._cap_component_enable(
        "consumer",
        "component.enable",
        {
            "name": "provider.public_api",
            "component_type": "API",
            "scope": "global",
            "stream_id": "",
        },
    )
    assert enable_result["success"] is True
    assert provider_supervisor.api_registry.get_api("provider", "public_api", enabled_only=True) is not None


@pytest.mark.asyncio
async def test_api_registry_supports_multiple_versions_with_distinct_handlers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """同名 API 不同版本应可并存，并按版本路由到不同处理器。"""

    provider_supervisor = PluginSupervisor(plugin_dirs=[])
    consumer_supervisor = PluginSupervisor(plugin_dirs=[])
    await _register_plugin(
        provider_supervisor,
        "provider",
        [
            {
                "name": "render_html",
                "component_type": "API",
                "metadata": {
                    "description": "渲染 HTML v1",
                    "version": "1",
                    "public": True,
                    "handler_name": "handle_render_html_v1",
                },
            },
            {
                "name": "render_html",
                "component_type": "API",
                "metadata": {
                    "description": "渲染 HTML v2",
                    "version": "2",
                    "public": True,
                    "handler_name": "handle_render_html_v2",
                },
            },
        ],
    )
    await _register_plugin(consumer_supervisor, "consumer", [])

    captured: Dict[str, Any] = {}

    async def fake_invoke_api(
        plugin_id: str,
        component_name: str,
        args: Dict[str, Any] | None = None,
        timeout_ms: int = 30000,
    ) -> Any:
        """模拟多版本 API 调用。"""

        captured["plugin_id"] = plugin_id
        captured["component_name"] = component_name
        captured["args"] = args or {}
        captured["timeout_ms"] = timeout_ms
        return SimpleNamespace(error=None, payload={"success": True, "result": {"image": "ok"}})

    monkeypatch.setattr(provider_supervisor, "invoke_api", fake_invoke_api)
    manager = _build_manager(provider_supervisor, consumer_supervisor)

    ambiguous_result = await manager._cap_api_call(
        "consumer",
        "api.call",
        {
            "api_name": "provider.render_html",
            "args": {"html": "<div>Hello</div>"},
        },
    )
    assert ambiguous_result["success"] is False
    assert "多个版本" in str(ambiguous_result["error"])

    disable_ambiguous_result = await manager._cap_component_disable(
        "consumer",
        "component.disable",
        {
            "name": "provider.render_html",
            "component_type": "API",
            "scope": "global",
            "stream_id": "",
        },
    )
    assert disable_ambiguous_result["success"] is False
    assert "多个版本" in str(disable_ambiguous_result["error"])

    disable_v1_result = await manager._cap_component_disable(
        "consumer",
        "component.disable",
        {
            "name": "provider.render_html",
            "component_type": "API",
            "scope": "global",
            "stream_id": "",
            "version": "1",
        },
    )
    assert disable_v1_result["success"] is True
    assert provider_supervisor.api_registry.get_api("provider", "render_html", version="1", enabled_only=True) is None
    assert provider_supervisor.api_registry.get_api("provider", "render_html", version="2", enabled_only=True) is not None

    result = await manager._cap_api_call(
        "consumer",
        "api.call",
        {
            "api_name": "provider.render_html",
            "version": "2",
            "args": {"html": "<div>Hello</div>"},
        },
    )

    assert result == {"success": True, "result": {"image": "ok"}}
    assert captured["plugin_id"] == "provider"
    assert captured["component_name"] == "handle_render_html_v2"
    assert captured["args"] == {"html": "<div>Hello</div>"}


@pytest.mark.asyncio
async def test_api_replace_dynamic_can_offline_removed_entries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """动态 API 替换后，被移除的 API 应返回明确下线错误。"""

    supervisor = PluginSupervisor(plugin_dirs=[])
    await _register_plugin(supervisor, "provider", [])
    manager = _build_manager(supervisor)

    captured: Dict[str, Any] = {}

    async def fake_invoke_api(
        plugin_id: str,
        component_name: str,
        args: Dict[str, Any] | None = None,
        timeout_ms: int = 30000,
    ) -> Any:
        """模拟动态 API 调用。"""

        captured["plugin_id"] = plugin_id
        captured["component_name"] = component_name
        captured["args"] = args or {}
        captured["timeout_ms"] = timeout_ms
        return SimpleNamespace(error=None, payload={"success": True, "result": {"ok": True}})

    monkeypatch.setattr(supervisor, "invoke_api", fake_invoke_api)

    replace_result = await manager._cap_api_replace_dynamic(
        "provider",
        "api.replace_dynamic",
        {
            "apis": [
                {
                    "name": "mcp.search",
                    "type": "API",
                    "metadata": {
                        "version": "1",
                        "public": True,
                        "handler_name": "dynamic_search",
                    },
                },
                {
                    "name": "mcp.read",
                    "type": "API",
                    "metadata": {
                        "version": "1",
                        "public": True,
                        "handler_name": "dynamic_read",
                    },
                },
            ],
            "offline_reason": "MCP 服务器已关闭",
        },
    )

    assert replace_result["success"] is True
    assert replace_result["count"] == 2
    list_result = await manager._cap_api_list("provider", "api.list", {"plugin_id": "provider"})
    assert {(item["name"], item["version"]) for item in list_result["apis"]} == {
        ("mcp.read", "1"),
        ("mcp.search", "1"),
    }

    call_result = await manager._cap_api_call(
        "provider",
        "api.call",
        {
            "api_name": "provider.mcp.search",
            "version": "1",
            "args": {"query": "hello"},
        },
    )
    assert call_result == {"success": True, "result": {"ok": True}}
    assert captured["component_name"] == "dynamic_search"
    assert captured["args"]["query"] == "hello"
    assert captured["args"]["__maibot_api_name__"] == "mcp.search"
    assert captured["args"]["__maibot_api_version__"] == "1"

    second_replace_result = await manager._cap_api_replace_dynamic(
        "provider",
        "api.replace_dynamic",
        {
            "apis": [
                {
                    "name": "mcp.read",
                    "type": "API",
                    "metadata": {
                        "version": "1",
                        "public": True,
                        "handler_name": "dynamic_read",
                    },
                }
            ],
            "offline_reason": "MCP 服务器已关闭",
        },
    )

    assert second_replace_result["success"] is True
    assert second_replace_result["count"] == 1
    assert second_replace_result["offlined"] == 1

    offlined_call_result = await manager._cap_api_call(
        "provider",
        "api.call",
        {
            "api_name": "provider.mcp.search",
            "version": "1",
            "args": {},
        },
    )
    assert offlined_call_result["success"] is False
    assert "MCP 服务器已关闭" in str(offlined_call_result["error"])

    list_after_replace = await manager._cap_api_list("provider", "api.list", {"plugin_id": "provider"})
    assert {(item["name"], item["version"]) for item in list_after_replace["apis"]} == {
        ("mcp.read", "1"),
    }
