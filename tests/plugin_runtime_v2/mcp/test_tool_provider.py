"""Task 4.2: MCPToolProvider 单元测试。"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest  # noqa: F401

from src.core.tooling import ToolInvocation
from src.plugin_runtime_v2.mcp.tool_provider import MCPToolProvider


def _make_td(name="t1", description="desc", params='{"type":"object"}', output=""):
    td = MagicMock()
    td.name = name
    td.description = description
    td.parameters_schema = params
    td.output_schema = output
    return td


class TestToolSpecMapping:
    def test_declaration_to_spec(self):
        td = _make_td()
        provider = MCPToolProvider("p1", "r1", [td], "localhost:9999")
        specs = provider._tool_specs
        assert len(specs) == 1
        s = specs[0]
        assert s.name == "t1"
        assert s.description == "desc"
        assert s.parameters_schema == {"type": "object"}
        assert s.provider_name == "p1"
        assert s.provider_type == "mcp_remote"

    def test_command_pattern_stripped(self):
        td = _make_td(params='{"type":"object","x-maibot-command-pattern":"/help"}')
        provider = MCPToolProvider("p1", "r1", [td], "localhost:9999")
        s = provider._tool_specs[0]
        assert "x-maibot-command-pattern" not in s.parameters_schema
        assert s.metadata["pattern"] == "/help"

    def test_empty_name_skipped(self):
        td = _make_td(name="")
        provider = MCPToolProvider("p1", "r1", [td], "localhost:9999")
        assert len(provider._tool_specs) == 0

    def test_invalid_schema_skipped_gracefully(self):
        td = _make_td(params="not json")
        provider = MCPToolProvider("p1", "r1", [td], "localhost:9999")
        assert len(provider._tool_specs) == 0


class TestListTools:

    @pytest.mark.asyncio
    async def test_list_tools_returns_cached(self):
        td = _make_td()
        provider = MCPToolProvider("p1", "r1", [td], "localhost:9999")
        tools = await provider.list_tools()
        assert len(tools) == 1
        assert tools[0].name == "t1"


class TestInvoke:

    @pytest.mark.asyncio
    async def test_invoke_success(self):
        td = _make_td()
        provider = MCPToolProvider("p1", "r1", [td], "localhost:9999")
        mock_stub = AsyncMock()
        mock_stub.InvokeTool.return_value = MagicMock(success=True, result='{"ok":1}', error="")
        provider._stub = mock_stub

        inv = ToolInvocation(tool_name="t1", arguments={}, call_id="c1", session_id="s1")
        res = await provider.invoke(inv)
        assert res.success
        assert json.loads(res.content) == {"ok": 1}

    @pytest.mark.asyncio
    async def test_invoke_runner_unavailable(self):
        provider = MCPToolProvider("p1", "r1", [], "localhost:9999")
        provider._stub = None
        provider._channel = None

        inv = ToolInvocation(tool_name="t1", arguments={}, call_id="c1", session_id="s1")
        res = await provider.invoke(inv)
        assert not res.success
        assert "不可用" in res.error_message
