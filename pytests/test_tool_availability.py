from types import SimpleNamespace
import importlib.util
import sys

import pytest

from src.core.tooling import ToolAvailabilityContext, ToolRegistry
from src.maisaka.tool_provider import MaisakaBuiltinToolProvider
from src.plugin_runtime.component_query import ComponentQueryService
from src.plugin_runtime.host.component_registry import ComponentRegistry


@pytest.mark.asyncio
async def test_builtin_at_is_exposed_only_in_group_chats() -> None:
    registry = ToolRegistry()
    registry.register_provider(MaisakaBuiltinToolProvider())

    group_specs = await registry.list_tools(ToolAvailabilityContext(session_id="group-1", is_group_chat=True))
    private_specs = await registry.list_tools(ToolAvailabilityContext(session_id="private-1", is_group_chat=False))
    default_specs = await registry.list_tools()

    assert "at" in {tool_spec.name for tool_spec in group_specs}
    assert "at" not in {tool_spec.name for tool_spec in private_specs}
    assert "at" in {tool_spec.name for tool_spec in default_specs}


def test_plugin_tool_chat_scope_uses_component_field(monkeypatch: pytest.MonkeyPatch) -> None:
    service = ComponentQueryService()
    registry = ComponentRegistry()
    supervisor = SimpleNamespace(component_registry=registry)
    monkeypatch.setattr(service, "_iter_supervisors", lambda: [supervisor])

    registry.register_plugin_components(
        "scope_plugin",
        [
            {
                "name": "group_tool",
                "component_type": "TOOL",
                "chat_scope": "group",
                "metadata": {"description": "group only"},
            },
            {
                "name": "private_tool",
                "component_type": "TOOL",
                "chat_scope": "private",
                "metadata": {"description": "private only"},
            },
            {
                "name": "all_tool",
                "component_type": "TOOL",
                "metadata": {"description": "all chats"},
            },
        ],
    )

    group_specs = service.get_llm_available_tool_specs(
        context=ToolAvailabilityContext(session_id="group-1", is_group_chat=True)
    )
    private_specs = service.get_llm_available_tool_specs(
        context=ToolAvailabilityContext(session_id="private-1", is_group_chat=False)
    )

    group_entry = registry.get_component("scope_plugin.group_tool")
    assert group_entry is not None
    assert group_entry.chat_scope == "group"
    assert "chat_scope" not in group_entry.metadata
    assert set(group_specs) == {"group_tool", "all_tool"}
    assert set(private_specs) == {"private_tool", "all_tool"}


def test_plugin_tool_session_disable_still_filters_specific_chat(monkeypatch: pytest.MonkeyPatch) -> None:
    service = ComponentQueryService()
    registry = ComponentRegistry()
    supervisor = SimpleNamespace(component_registry=registry)
    monkeypatch.setattr(service, "_iter_supervisors", lambda: [supervisor])

    registry.register_plugin_components(
        "mute_plugin",
        [
            {
                "name": "mute",
                "component_type": "TOOL",
                "chat_scope": "group",
                "metadata": {"description": "mute group member"},
            }
        ],
    )
    registry.set_component_enabled("mute_plugin.mute", False, session_id="group-disabled")

    disabled_specs = service.get_llm_available_tool_specs(
        context=ToolAvailabilityContext(session_id="group-disabled", is_group_chat=True)
    )
    enabled_specs = service.get_llm_available_tool_specs(
        context=ToolAvailabilityContext(session_id="group-enabled", is_group_chat=True)
    )

    assert "mute" not in disabled_specs
    assert "mute" in enabled_specs


def test_plugin_tool_allowed_session_filters_tool_exposure(monkeypatch: pytest.MonkeyPatch) -> None:
    service = ComponentQueryService()
    registry = ComponentRegistry()
    supervisor = SimpleNamespace(component_registry=registry)
    monkeypatch.setattr(service, "_iter_supervisors", lambda: [supervisor])

    registry.register_plugin_components(
        "mute_plugin",
        [
            {
                "name": "mute",
                "component_type": "TOOL",
                "chat_scope": "group",
                "allowed_session": ["qq:10001", "raw-group-id", "exact-session-id"],
                "metadata": {"description": "mute group member"},
            }
        ],
    )

    platform_group_specs = service.get_llm_available_tool_specs(
        context=ToolAvailabilityContext(
            session_id="hashed-session-1",
            is_group_chat=True,
            group_id="10001",
            platform="qq",
        )
    )
    raw_group_specs = service.get_llm_available_tool_specs(
        context=ToolAvailabilityContext(
            session_id="hashed-session-2",
            is_group_chat=True,
            group_id="raw-group-id",
            platform="qq",
        )
    )
    exact_session_specs = service.get_llm_available_tool_specs(
        context=ToolAvailabilityContext(session_id="exact-session-id", is_group_chat=True)
    )
    blocked_specs = service.get_llm_available_tool_specs(
        context=ToolAvailabilityContext(
            session_id="blocked-session",
            is_group_chat=True,
            group_id="20002",
            platform="qq",
        )
    )

    entry = registry.get_component("mute_plugin.mute")
    assert entry is not None
    assert entry.allowed_session == {"qq:10001", "raw-group-id", "exact-session-id"}
    assert "allowed_session" not in entry.metadata
    assert "mute" in platform_group_specs
    assert "mute" in raw_group_specs
    assert "mute" in exact_session_specs
    assert "mute" not in blocked_specs


def test_plugin_tool_disabled_session_take_precedence_over_allowed_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = ComponentQueryService()
    registry = ComponentRegistry()
    supervisor = SimpleNamespace(component_registry=registry)
    monkeypatch.setattr(service, "_iter_supervisors", lambda: [supervisor])

    registry.register_plugin_components(
        "mute_plugin",
        [
            {
                "name": "mute",
                "component_type": "TOOL",
                "chat_scope": "group",
                "allowed_session": ["qq:10001"],
                "metadata": {"description": "mute group member"},
            }
        ],
    )
    registry.set_component_enabled("mute_plugin.mute", False, session_id="allowed-session")

    visible_specs = service.get_llm_available_tool_specs(
        context=ToolAvailabilityContext(
            session_id="visible-session",
            is_group_chat=True,
            group_id="10001",
            platform="qq",
        )
    )
    disabled_specs = service.get_llm_available_tool_specs(
        context=ToolAvailabilityContext(
            session_id="allowed-session",
            is_group_chat=True,
            group_id="10001",
            platform="qq",
        )
    )

    entry = registry.get_component("mute_plugin.mute")
    assert entry is not None
    assert entry.disabled_session == {"allowed-session"}
    assert "mute" in visible_specs
    assert "mute" not in disabled_specs


def test_mute_plugin_exports_allowed_groups_as_component_allowed_session() -> None:
    module_path = "plugins/MutePlugin/plugin.py"
    spec = importlib.util.spec_from_file_location("mute_plugin_under_test", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.MutePluginConfig.model_rebuild()

    plugin = module.MutePlugin()
    plugin.set_plugin_config({"permissions": {"allowed_groups": ["qq:10001", "raw-group-id"]}})

    mute_components = [component for component in plugin.get_components() if component.get("name") == "mute"]

    assert len(mute_components) == 1
    assert mute_components[0]["chat_scope"] == "group"
    assert mute_components[0]["allowed_session"] == ["qq:10001", "raw-group-id"]
    assert "allowed_session" not in mute_components[0]["metadata"]
