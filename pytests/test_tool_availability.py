from types import SimpleNamespace

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
