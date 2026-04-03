"""StrReplaceFile tool for AgentLite.

This module provides a tool for editing files using string replacement.
"""

from __future__ import annotations

from pathlib import Path
from typing import Union

from pydantic import BaseModel, Field

from agentlite.tool import CallableTool2, ToolError, ToolOk, ToolResult


class Edit(BaseModel):
    """A single edit operation."""

    old: str = Field(description="The old string to replace. Can be multi-line.")
    new: str = Field(description="The new string to replace with. Can be multi-line.")
    replace_all: bool = Field(
        description="Whether to replace all occurrences.",
        default=False,
    )


class Params(BaseModel):
    """Parameters for the StrReplaceFile tool."""

    path: str = Field(
        description=(
            "The path to the file to edit. Absolute paths are required when editing files "
            "outside the working directory."
        )
    )
    edit: Union[Edit, list[Edit]] = Field(
        description=(
            "The edit(s) to apply to the file. "
            "You can provide a single edit or a list of edits here."
        ),
    )


class StrReplaceFile(CallableTool2[Params]):
    """Tool for editing files using string replacement.

    This tool replaces strings in a file. It can perform single or multiple
    replacements, and optionally replace all occurrences.

    Example:
        >>> tool = StrReplaceFile(work_dir=Path("/tmp"))
        >>> result = await tool({"path": "test.txt", "edit": {"old": "Hello", "new": "Hi"}})
    """

    name: str = "StrReplaceFile"
    description: str = (
        "Edit a file by replacing strings. "
        "Supports single or multiple edits, and can replace all occurrences. "
        "The old string must match exactly (including whitespace)."
    )
    params: type[Params] = Params

    def __init__(
        self,
        work_dir: Path,
        allow_outside_work_dir: bool = False,
    ):
        """Initialize the StrReplaceFile tool.

        Args:
            work_dir: The working directory for relative paths
            allow_outside_work_dir: Whether to allow editing outside the working directory
        """
        super().__init__()
        self._work_dir = work_dir
        self._allow_outside_work_dir = allow_outside_work_dir

    def _is_within_work_dir(self, path: Path) -> bool:
        """Check if a path is within the working directory."""
        try:
            path.relative_to(self._work_dir.resolve())
            return True
        except ValueError:
            return False

    def _apply_edit(self, content: str, edit: Edit) -> tuple[str, int]:
        """Apply a single edit to the content.

        Args:
            content: The original content
            edit: The edit to apply

        Returns:
            Tuple of (new_content, replacements_count)
        """
        if edit.replace_all:
            count = content.count(edit.old)
            new_content = content.replace(edit.old, edit.new)
            return new_content, count
        else:
            if edit.old in content:
                new_content = content.replace(edit.old, edit.new, 1)
                return new_content, 1
            return content, 0

    async def __call__(self, params: Params) -> ToolResult:
        """Execute the string replacement operation.

        Args:
            params: The edit parameters

        Returns:
            ToolResult with success message or error
        """
        if not params.path:
            return ToolError(
                message="File path cannot be empty.",
            )

        try:
            # Resolve path
            path = Path(params.path).expanduser()
            if not path.is_absolute():
                path = self._work_dir / path
            path = path.resolve()

            # Security check
            if not self._is_within_work_dir(path):
                if not Path(params.path).is_absolute():
                    return ToolError(
                        message=(
                            f"`{params.path}` is not an absolute path. "
                            "You must provide an absolute path to edit a file "
                            "outside the working directory."
                        ),
                    )
                if not self._allow_outside_work_dir:
                    return ToolError(
                        message=(
                            f"Editing outside the working directory is not allowed. "
                            f"Path: {params.path}"
                        ),
                    )

            # Check file exists
            if not path.exists():
                return ToolError(
                    message=f"`{params.path}` does not exist.",
                )

            if not path.is_file():
                return ToolError(
                    message=f"`{params.path}` is not a file.",
                )

            # Read file content
            content = path.read_text(encoding="utf-8", errors="replace")
            original_content = content

            # Normalize edits to list
            edits = [params.edit] if isinstance(params.edit, Edit) else params.edit

            # Apply edits
            total_replacements = 0
            for edit in edits:
                content, count = self._apply_edit(content, edit)
                total_replacements += count

            # Check if any changes were made
            if content == original_content:
                return ToolError(
                    message="No replacements were made. The old string was not found in the file.",
                )

            # Write back
            path.write_text(content, encoding="utf-8")

            return ToolOk(
                output="",
                message=(
                    f"File successfully edited. "
                    f"Applied {len(edits)} edit(s) with {total_replacements} total replacement(s)."
                ),
            )

        except Exception as e:
            return ToolError(
                message=f"Failed to edit {params.path}. Error: {e}",
            )
