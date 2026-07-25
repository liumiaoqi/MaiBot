"""Task 6.3+7.6: MCPHostBridge 单元测试 + 回调注入。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.core.tooling import ToolInvocation, ToolExecutionContext, ToolRegistry
from src.plugin_runtime_v2.mcp.host_bridge import MCPHostBridge
from src.plugin_runtime_v2.mcp.event_dispatcher import EventDispatcher


def _make_tool_decl(name="t1", desc="desc"):
    td = MagicMock()
    td.name = name
    td.description = desc
    td.parameters_schema = ""
    td.output_schema = ""
    return td


class TestOnRunnerRegistered:

    def test_registered_creates_provider(self):
        registry = ToolRegistry()
        dispatcher = EventDispatcher()
        person_port = MagicMock()
        bridge = MCPHostBridge(registry, dispatcher, person_port)

        tools = [_make_tool_decl("t1")]
        bridge.on_runner_registered("r1", "p1", tools, [], "localhost:9999")
        assert "p1" in bridge._providers

    @pytest.mark.asyncio
    async def test_duplicate_registration_skipped(self):
        registry = ToolRegistry()
        dispatcher = EventDispatcher()
        person_port = MagicMock()
        bridge = MCPHostBridge(registry, dispatcher, person_port)

        bridge.on_runner_registered("r1", "p1", [_make_tool_decl()], [], "localhost:9999")
        bridge.on_runner_registered("r1", "p1", [_make_tool_decl()], [], "localhost:9999")
        assert len(bridge._providers) == 1

    def test_empty_tools_events_skipped(self):
        registry = ToolRegistry()
        dispatcher = EventDispatcher()
        person_port = MagicMock()
        bridge = MCPHostBridge(registry, dispatcher, person_port)

        bridge.on_runner_registered("r1", "p1", [], [], "localhost:9999")
        assert len(bridge._providers) == 0


class TestInjectCommandContext:

    def test_injects_context_fields(self):
        registry = ToolRegistry()
        dispatcher = EventDispatcher()
        person_port = MagicMock()
        person_port.get_person_info.return_value = MagicMock(person_name="Alice")
        bridge = MCPHostBridge(registry, dispatcher, person_port)

        inv = ToolInvocation(tool_name="cmd_help", arguments={}, call_id="c1", session_id="")
        ctx = ToolExecutionContext(
            session_id="sid", user_id="uid", is_group_chat=True,
        )
        bridge._inject_command_context(inv, ctx, {"pattern": "/help"})

        assert inv.arguments["session_id"] == "sid"
        assert inv.arguments["sender_id"] == "uid"
        assert inv.arguments["sender_name"] == "Alice"
        assert inv.arguments["is_group_chat"] is True

    def test_no_pattern_skips_injection(self):
        bridge = MCPHostBridge(ToolRegistry(), EventDispatcher(), MagicMock())
        inv = ToolInvocation(tool_name="t1", arguments={}, call_id="c1", session_id="")
        ctx = ToolExecutionContext(session_id="s", user_id="u", is_group_chat=False)
        bridge._inject_command_context(inv, ctx, {})
        assert inv.arguments == {}
