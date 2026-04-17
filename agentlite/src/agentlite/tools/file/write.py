"""WriteFile tool for AgentLite.

This module provides a tool for writing files to the filesystem.
"""

from __future__ import annotations
from typing import Literal

from pathlib import Path

from pydantic import BaseModel, Field

from agentlite.tool import CallableTool2, ToolError, ToolOk, ToolResult


class Params(BaseModel):
    """Parameters for the WriteFile tool."""

    path: str = Field(
        description=(
            "The path to the file to write. Absolute paths are required when writing files "
            "outside the working directory."
        )
    )
    content: str = Field(description="The content to write to the file")
    mode: Literal["overwrite", "append"] = Field(
        description=(
            "The mode to use to write to the file. "
            "Two modes are supported: `overwrite` for overwriting the whole file and "
            "`append` for appending to the end of an existing file."
        ),
        default="overwrite",
    )


class WriteFile(CallableTool2[Params]):
    """Tool for writing files to the filesystem.

    This tool writes content to a file, either overwriting or appending.

    Example:
        >>> tool = WriteFile(work_dir=Path("/tmp"))
        >>> result = await tool({"path": "test.txt", "content": "Hello World"})
    """

    name: str = "WriteFile"
    description: str = (
        "Write content to a file on the local filesystem. "
        "Can create new files or overwrite/append to existing files."
    )
    params: type[Params] = Params

    def __init__(
        self,
        work_dir: Path,
        allow_outside_work_dir: bool = False,
    ):
        """Initialize the WriteFile tool.

        Args:
            work_dir: The working directory for relative paths
            allow_outside_work_dir: Whether to allow writing outside the working directory
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
    async def __call__(self, params: Params) -> ToolResult:
        """Execute the write file operation.

        Args:
            params: The write parameters

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
                            "You must provide an absolute path to write a file "
                            "outside the working directory."
                        ),
                    )
                if not self._allow_outside_work_dir:
                    return ToolError(
                        message=(
                            f"Writing outside the working directory is not allowed. "
                            f"Path: {params.path}"
                        ),
                    )

            # Check parent directory exists
            if not path.parent.exists():
                return ToolError(
                    message=f"Parent directory `{path.parent}` does not exist.",
                )

            # Check valid mode
            if params.mode not in ("overwrite", "append"):
                return ToolError(
                    message=f"Invalid mode: {params.mode}. Must be 'overwrite' or 'append'.",
                )

            # Check if file exists
            file_existed = path.exists()
            old_content = ""
            if file_existed and path.is_file():
                old_content = path.read_text(encoding="utf-8", errors="replace")

            # Calculate new content
            if params.mode == "append" and file_existed:
                new_content = old_content + params.content
            else:
                new_content = params.content

            # Write file
            path.write_text(new_content, encoding="utf-8")

            # Build success message
            action = (
                "overwritten"
                if params.mode == "overwrite" and file_existed
                else ("appended to" if params.mode == "append" and file_existed else "created")
            )
            file_size = path.stat().st_size

            return ToolOk(
                output="",
                message=f"File `{params.path}` successfully {action}. Size: {file_size} bytes.",
            )

        except Exception as e:
            return ToolError(
                message=f"Failed to write to {params.path}. Error: {e}",
            )
