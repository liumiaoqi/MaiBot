"""MCP 工具 Provider。"""

from __future__ import annotations

from typing import Optional

from src.core.tooling import ToolExecutionContext, ToolExecutionResult, ToolInvocation, ToolProvider, ToolSpec

from .manager import MCPManager


class MCPToolProvider(ToolProvider):
    """基于 MCPManager 的工具 Provider。"""

    provider_name = "mcp"
    provider_type = "mcp"

    def __init__(self, manager: MCPManager) -> None:
        """初始化 MCP 工具 Provider。

        Args:
            manager: MCP 管理器实例。
        """

        self._manager = manager

    async def list_tools(self) -> list[ToolSpec]:
        """列出全部 MCP 工具。"""

        return self._manager.get_tool_specs()

    async def invoke(
        self,
        invocation: ToolInvocation,
        context: Optional[ToolExecutionContext] = None,
    ) -> ToolExecutionResult:
        """执行指定 MCP 工具。

        Args:
            invocation: 工具调用请求。
            context: 执行上下文。

        Returns:
            ToolExecutionResult: 工具执行结果。
        """

        del context
        return await self._manager.call_tool_invocation(invocation)

    async def close(self) -> None:
        """关闭 Provider 并释放 MCP 连接。"""

        await self._manager.close()

