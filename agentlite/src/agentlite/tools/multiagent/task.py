"""Task tool for AgentLite.

This module provides a tool for delegating tasks to subagents.

In this rdev subagent integration, nested subagents are intentionally
disabled. The tool is kept for API compatibility but no longer executes
delegation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from agentlite.tool import CallableTool2, ToolError, ToolResult

if TYPE_CHECKING:
    from agentlite.agent import Agent
    from agentlite.labor_market import LaborMarket


class Params(BaseModel):
    """Parameters for the Task tool."""

    subagent_name: str = Field(description="The name of the subagent to call (must be registered)")
    prompt: str = Field(
        description=(
            "The task for the subagent to perform. "
            "Provide detailed instructions with all necessary context."
        ),
    )
    description: str = Field(
        default="",
        description="A short (3-5 word) description of the task (for logging)",
    )


class Task(CallableTool2[Params]):
    """Tool for delegating tasks to subagents.

    This tool allows a parent agent to delegate tasks to its subagents.
    The subagent must be registered in the parent's labor market.

    Example:
        >>> # Parent agent has a "coder" subagent
        >>> tool = Task(parent_agent)
        >>> result = await tool(
        ...     {
        ...         "subagent_name": "coder",
        ...         "prompt": "Write a Python function to sort a list",
        ...         "description": "Write sorting function",
        ...     }
        ... )
    """

    name: str = "Task"
    description: str = (
        "Delegate a task to a specialized subagent. "
        "The subagent must be registered in the parent agent's labor market. "
        "The subagent will execute independently and return its findings."
    )
    params: type[Params] = Params

    def __init__(
        self,
        labor_market: LaborMarket | None = None,
        parent_agent: Agent | None = None,
        max_iterations: int = 80,
    ):
        """Initialize the Task tool.

        Args:
            labor_market: The LaborMarket containing subagents
            parent_agent: Alternative: the parent agent (uses its labor_market)
            max_iterations: Maximum iterations for subagent execution

        Raises:
            ValueError: If neither labor_market nor parent_agent is provided.
        """
        super().__init__()

        if labor_market is not None:
            self._labor_market = labor_market
        elif parent_agent is not None:
            self._labor_market = parent_agent.labor_market
        else:
            raise ValueError("Either labor_market or parent_agent must be provided")

        self._max_iterations = max_iterations

    async def __call__(self, params: Params) -> ToolResult:
        """Refuse to execute nested subagent delegation."""
        return ToolError(
            message=(
                "Task tool is disabled in this subagent runtime. "
                f"Nested subagent delegation is not allowed (requested '{params.subagent_name}')."
            ),
        )
