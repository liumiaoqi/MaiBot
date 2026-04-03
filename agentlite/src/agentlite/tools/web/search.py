"""SearchWeb tool for AgentLite.

This module provides a tool for web search.

Note: This is a placeholder implementation. A real implementation would
require integration with a search API like Google, Bing, or DuckDuckGo.
"""

from __future__ import annotations


from pydantic import BaseModel, Field

from agentlite.tool import CallableTool2, ToolError, ToolResult


class Params(BaseModel):
    """Parameters for the SearchWeb tool."""

    query: str = Field(description="The search query string.")
    num_results: int = Field(
        description="Number of search results to return (max 10).",
        default=5,
        ge=1,
        le=10,
    )


class SearchWeb(CallableTool2[Params]):
    """Tool for web search.

    This tool performs a web search and returns relevant results.

    Note: This is a placeholder implementation. To use real search functionality,
    you need to integrate with a search API (Google, Bing, DuckDuckGo, etc.)
    and set the appropriate API keys.

    Example:
        >>> tool = SearchWeb()
        >>> result = await tool({"query": "Python async programming"})
    """

    name: str = "SearchWeb"
    description: str = (
        "Search the web for information. "
        "Returns a list of relevant search results with titles and snippets. "
        "Note: Requires search API configuration to work properly."
    )
    params: type[Params] = Params

    def __init__(
        self,
        timeout: int = 30,
        user_agent: str = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"),
    ):
        """Initialize the SearchWeb tool.

        Args:
            timeout: Request timeout in seconds
            user_agent: User-Agent string
        """
        super().__init__()
        self._timeout = timeout
        self._user_agent = user_agent
    async def __call__(self, params: Params) -> ToolResult:
        """Execute the web search.

        Args:
            params: The search parameters

        Returns:
            ToolResult with search results or error
        """
        if not params.query:
            return ToolError(message="Search query cannot be empty.")

        return ToolError(
            message=(
                "SearchWeb tool is disabled in this subagent runtime. "
                "Use FetchURL for direct URL content retrieval."
            ),
        )
