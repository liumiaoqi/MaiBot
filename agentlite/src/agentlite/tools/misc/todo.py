"""SetTodoList tool for AgentLite.

This module provides a tool for managing todo lists.
"""

from __future__ import annotations
from typing import Literal


from pydantic import BaseModel, Field

from agentlite.tool import CallableTool2, ToolOk, ToolResult


class Todo(BaseModel):
    """A single todo item."""

    title: str = Field(description="The title of the todo", min_length=1)
    status: Literal["pending", "in_progress", "done"] = Field(description="The status of the todo")


class Params(BaseModel):
    """Parameters for the SetTodoList tool."""

    todos: list[Todo] = Field(description="The todo list to set")


class SetTodoList(CallableTool2[Params]):
    """Tool for managing todo lists.

    This tool allows the agent to create and update a todo list.
    The todo list can be used to track tasks and progress.

    Example:
        >>> tool = SetTodoList()
        >>> result = await tool(
        ...     {
        ...         "todos": [
        ...             {"title": "Read docs", "status": "done"},
        ...             {"title": "Write code", "status": "in_progress"},
        ...         ]
        ...     }
        ... )
    """

    name: str = "SetTodoList"
    description: str = (
        "Set or update the todo list. "
        "Use this to track tasks and show progress. "
        "Each todo has a title and status (pending/in_progress/done)."
    )
    params: type[Params] = Params

    def __init__(self):
        """Initialize the SetTodoList tool."""
        super().__init__()
        self._todos: list[Todo] = []
    async def __call__(self, params: Params) -> ToolResult:
        """Execute the todo list update.

        Args:
            params: The todo list parameters

        Returns:
            ToolResult with success message
        """
        self._todos = params.todos

        # Format output
        lines = []
        for todo in self._todos:
            status_emoji = {
                "pending": "⏳",
                "in_progress": "🔨",
                "done": "✅",
            }.get(todo.status, "❓")
            lines.append(f"{status_emoji} {todo.title}")

        output = "\n".join(lines) if lines else "No todos."

        # Count by status
        counts = {"pending": 0, "in_progress": 0, "done": 0}
        for todo in self._todos:
            if todo.status in counts:
                counts[todo.status] += 1

        message = (
            f"Todo list updated: {len(self._todos)} items "
            f"({counts['done']} done, {counts['in_progress']} in progress, "
            f"{counts['pending']} pending)"
        )

        return ToolOk(output=output, message=message)

    def get_todos(self) -> list[Todo]:
        """Get the current todo list.

        Returns:
            The current list of todos
        """
        return self._todos.copy()
