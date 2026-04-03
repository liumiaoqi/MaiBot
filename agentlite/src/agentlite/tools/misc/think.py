"""Think tool for AgentLite.

This module provides a tool for recording thoughts.
"""

from __future__ import annotations


from pydantic import BaseModel, Field

from agentlite.tool import CallableTool2, ToolOk, ToolResult


class Params(BaseModel):
    """Parameters for the Think tool."""

    thought: str = Field(description="A thought to record")


class Think(CallableTool2[Params]):
    """Tool for recording thoughts.

    This tool allows the agent to record its thinking process.
    Useful for debugging and understanding the agent's reasoning.

    Example:
        >>> tool = Think()
        >>> result = await tool({"thought": "I should first check if the file exists..."})
    """

    name: str = "Think"
    description: str = (
        "Record a thought or reasoning step. "
        "Use this to think through problems before taking action. "
        "The thought will be logged but not returned to the user."
    )
    params: type[Params] = Params

    def __init__(self):
        """Initialize the Think tool."""
        super().__init__()
        self._thoughts: list[str] = []
    async def __call__(self, params: Params) -> ToolResult:
        """Execute the thought recording.

        Args:
            params: The thought parameters

        Returns:
            ToolResult with success message
        """
        self._thoughts.append(params.thought)

        return ToolOk(
            output="",
            message=f"Thought recorded ({len(self._thoughts)} total thoughts)",
        )

    def get_thoughts(self) -> list[str]:
        """Get all recorded thoughts.

        Returns:
            List of all recorded thoughts
        """
        return self._thoughts.copy()

    def clear_thoughts(self) -> None:
        """Clear all recorded thoughts."""
        self._thoughts.clear()
