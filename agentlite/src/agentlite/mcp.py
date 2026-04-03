"""MCP (Model Context Protocol) integration for AgentLite.

This module provides integration with MCP servers, allowing agents to use
tools from external MCP-compatible servers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agentlite.tool import CallableTool, ToolOk, ToolResult, ToolError

if TYPE_CHECKING:
    pass


class MCPClient:
    """Client for connecting to MCP servers.

    This client allows you to connect to MCP servers and load their tools
    into AgentLite agents.

    Example:
        >>> client = MCPClient()
        >>> await client.connect_stdio(
        ...     "npx", ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
        ... )
        >>> tools = await client.load_tools()
        >>> agent = Agent(provider=provider, tools=tools)
    """

    def __init__(self):
        """Initialize the MCP client."""
        self._client: Any | None = None
        self._connected = False

    def _check_fastmcp(self) -> None:
        """Check if fastmcp is installed."""
        try:
            import fastmcp  # noqa: F401
        except ImportError as e:
            raise ImportError(
                "MCP support requires 'fastmcp' package. Install with: pip install agentlite[mcp]"
            ) from e

    async def connect_stdio(
        self,
        command: str,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        """Connect to an MCP server via stdio.

        Args:
            command: The command to run.
            args: Optional arguments for the command.
            env: Optional environment variables.

        Raises:
            RuntimeError: If already connected.
            ConnectionError: If the connection fails.
        """
        if self._connected:
            raise RuntimeError("Already connected to an MCP server")

        try:
            from fastmcp import Client
            from fastmcp.client.transports import PythonStdioTransport

            transport = PythonStdioTransport(
                command_or_script=command,
                args=args or [],
                env=env,
            )
            self._client = Client(transport)
            self._connected = True
        except Exception as e:
            raise ConnectionError(f"Failed to connect to MCP server: {e}") from e

    async def connect_sse(
        self,
        url: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Connect to an MCP server via Server-Sent Events (SSE).

        Args:
            url: The SSE endpoint URL.
            headers: Optional headers to include in requests.

        Raises:
            RuntimeError: If already connected.
            ConnectionError: If the connection fails.
        """
        if self._connected:
            raise RuntimeError("Already connected to an MCP server")

        try:
            from fastmcp import Client
            from fastmcp.client.transports import SSETransport

            transport = SSETransport(url=url, headers=headers)
            self._client = Client(transport)
            self._connected = True
        except Exception as e:
            raise ConnectionError(f"Failed to connect to MCP server: {e}") from e

    async def load_tools(self) -> list[CallableTool]:
        """Load tools from the connected MCP server.

        Returns:
            A list of CallableTool instances wrapping the MCP tools.

        Raises:
            RuntimeError: If not connected to an MCP server.
        """
        if not self._connected or self._client is None:
            raise RuntimeError("Not connected to an MCP server")

        tools: list[CallableTool] = []

        try:
            async with self._client as client:
                mcp_tools = await client.list_tools()

                for mcp_tool in mcp_tools:
                    tool = _MCPTool(
                        client=self._client,
                        name=mcp_tool.name,
                        description=mcp_tool.description or "No description provided",
                        parameters=mcp_tool.inputSchema,
                    )
                    tools.append(tool)
        except Exception as e:
            raise RuntimeError(f"Failed to load MCP tools: {e}") from e

        return tools

    async def close(self) -> None:
        """Close the connection to the MCP server."""
        if self._client is not None:
            try:
                await self._client.close()
            except Exception:
                pass
            finally:
                self._client = None
                self._connected = False

    async def __aenter__(self) -> MCPClient:
        """Async context manager entry."""
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        await self.close()


class _MCPTool(CallableTool):
    """Wrapper for MCP tools."""

    def __init__(
        self,
        client: Any,
        name: str,
        description: str,
        parameters: dict[str, Any],
    ):
        """Initialize the MCP tool wrapper.

        Args:
            client: The MCP client.
            name: The tool name.
            description: The tool description.
            parameters: The JSON schema for tool parameters.
        """
        self._client = client
        super().__init__(
            name=name,
            description=description,
            parameters=parameters,
        )

    async def __call__(self, **kwargs: Any) -> ToolResult:
        """Execute the MCP tool.

        Args:
            **kwargs: The tool arguments.

        Returns:
            The tool result.
        """
        try:
            async with self._client as client:
                result = await client.call_tool(self.name, kwargs)

                # Convert MCP result to ToolResult
                content_parts = []
                for content in result.content:
                    if hasattr(content, "text"):
                        content_parts.append(content.text)
                    else:
                        content_parts.append(str(content))

                output = "\n".join(content_parts)

                if result.isError:
                    return ToolError(message=output or "Tool execution failed")

                return ToolOk(output=output)
        except Exception as e:
            return ToolError(message=f"MCP tool execution failed: {e}")
