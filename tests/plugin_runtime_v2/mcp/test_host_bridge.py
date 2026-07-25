"""Task 6.3+7.6: MCPHostBridge 单元测试 + 回调注入。"""

from __future__ import annotations

from unittest.mock import MagicMock, Mock

from src.core.tooling import ToolInvocation, ToolExecutionContext, ToolRegistry
from src.plugin_runtime_v2.mcp.host_bridge import MCPHostBridge
from src.plugin_runtime_v2.mcp.event_dispatcher import EventDispatcher
from src.plugin_runtime_v2.host.connection import RunnerConnection, ConnectionState


def _make_conn(runner_id="r1", plugin_id="p1", tools=None, events=None, listen_addr="localhost:9999"):
    return RunnerConnection(
        runner_id=runner_id,
        state=ConnectionState.READY,
        sdk_version="4.0.0",
        session_token="t",
        scopes=["message:send:text"],
        tools=tools or [],
        events=events or [],
        plugin_id=plugin_id,
        runner_listen_address=listen_addr,
    )


def _make_tool_decl(name="t1", desc="desc"):
    td = MagicMock()
    td.name = name
    td.description = desc
    td.parameters_schema = ""
    td.output_schema = ""
    return td


def _make_event_decl(name="e1", desc="desc"):
    ed = MagicMock()
    ed.name = name
    ed.description = desc
    ed.card_metadata = None
    return ed


class TestOnRunnerRegistered:
    def test_registered_creates_provider(self):
        registry = ToolRegistry()
        dispatcher = EventDispatcher()
        person_port = MagicMock()
        bridge = MCPHostBridge(registry, dispatcher, person_port)

        tools = [_make_tool_decl("t1")]
        conn = _make_conn(tools=tools)
        bridge.on_runner_registered(conn)
        assert "r1" in bridge._providers

    def test_duplicate_registration_skipped(self):
        registry = ToolRegistry()
        dispatcher = EventDispatcher()
        person_port = MagicMock()
        bridge = MCPHostBridge(registry, dispatcher, person_port)

        conn = _make_conn(tools=[_make_tool_decl()])
        bridge.on_runner_registered(conn)
        bridge.on_runner_registered(conn)  # should skip
        assert len(bridge._providers) == 1

    def test_empty_tools_events_skipped(self):
        registry = ToolRegistry()
        dispatcher = EventDispatcher()
        person_port = MagicMock()
        bridge = MCPHostBridge(registry, dispatcher, person_port)

        conn = _make_conn()
        bridge.on_runner_registered(conn)
        assert len(bridge._providers) == 0


class TestInjectCommandContext:
    def test_injects_context_fields(self):
        registry = ToolRegistry()
        dispatcher = EventDispatcher()
        person_port = MagicMock()
        person_port.get_person_info.return_value = Mock(person_name="Alice")
        bridge = MCPHostBridge(registry, dispatcher, person_port)

        inv = ToolInvocation(tool_name="cmd_help", arguments={}, call_id="c1", session_id="")
        ctx = ToolExecutionContext(
            session_id="sid", user_id="uid", is_group_chat=True, agent_id="", intent_type="",
        )
        bridge.inject_command_context(inv, ctx, {"pattern": "/help"})

        assert inv.arguments["session_id"] == "sid"
        assert inv.arguments["sender_id"] == "uid"
        assert inv.arguments["sender_name"] == "Alice"
        assert inv.arguments["is_group_chat"] is True

    def test_no_pattern_skips_injection(self):
        bridge = MCPHostBridge(ToolRegistry(), EventDispatcher(), MagicMock())
        inv = ToolInvocation(tool_name="t1", arguments={}, call_id="c1", session_id="")
        ctx = ToolExecutionContext(session_id="s", user_id="u", is_group_chat=False, agent_id="", intent_type="")
        bridge.inject_command_context(inv, ctx, {})
        assert inv.arguments == {}
