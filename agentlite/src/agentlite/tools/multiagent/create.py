"""CreateSubagent tool for AgentLite.

This module provides a tool for dynamically creating subagents.

In this rdev subagent integration, nested subagents are intentionally
disabled. The tool is kept for API compatibility but it intentionally
returns an explicit disabled error.
"""

from __future__ import annotations


from pydantic import BaseModel, Field

from agentlite.tool import CallableTool2, ToolError, ToolResult


class Params(BaseModel):
    """Parameters for the CreateSubagent tool."""

    name: str = Field(description="The name of the subagent to create")
    prompt: str = Field(
        description=(
            "The system prompt for the subagent. "
            "This defines the subagent's personality and capabilities."
        ),
    )


class CreateSubagent(CallableTool2[Params]):
    """Tool for dynamically creating subagents.

    This tool creates a new subagent with a custom system prompt.
    The subagent can then be used with the Task tool.

    Example:
        >>> tool = CreateSubagent()
        >>> result = await tool({"name": "researcher", "prompt": "You are a research assistant..."})
    """

    name: str = "CreateSubagent"
    description: str = (
        "Create a new subagent with a custom system prompt. "
        "The subagent can be used to perform specialized tasks. "
        "Use the Task tool to run tasks with created subagents."
    )
    params: type[Params] = Params

    def __init__(self):
        """Initialize the CreateSubagent tool."""
        super().__init__()
    async def __call__(self, params: Params) -> ToolResult:
        """Refuse to create nested subagents."""
        return ToolError(
            message=(
                "CreateSubagent tool is disabled in this subagent runtime. "
                f"Dynamic subagent creation is not allowed (requested '{params.name}')."
            ),
        )
