"""Glob tool for AgentLite.

This module provides a tool for searching files using glob patterns.
"""

from __future__ import annotations
from typing import Optional

from pathlib import Path

from pydantic import BaseModel, Field

from agentlite.tool import CallableTool2, ToolError, ToolOk, ToolResult


class Params(BaseModel):
    """Parameters for the Glob tool."""

    pattern: str = Field(
        description="Glob pattern to match files/directories (e.g., '*.py', '**/*.txt')"
    )
    directory: Optional[str] = Field(
        description=(
            "Absolute path to the directory to search in (defaults to working directory)."
        ),
        default=None,
    )
    include_dirs: bool = Field(
        description="Whether to include directories in results.",
        default=True,
    )


class Glob(CallableTool2[Params]):
    """Tool for searching files using glob patterns.

    This tool finds files and directories matching a glob pattern.
    Supports recursive patterns with **.

    Example:
        >>> tool = Glob(work_dir=Path("/tmp"))
        >>> result = await tool({"pattern": "*.py"})
    """

    name: str = "Glob"
    description: str = (
        "Search for files and directories matching a glob pattern. "
        "Supports recursive patterns with **. "
        "Returns paths relative to the search directory."
    )
    params: type[Params] = Params

    def __init__(
        self,
        work_dir: Path,
        max_matches: int = 1000,
    ):
        """Initialize the Glob tool.

        Args:
            work_dir: The working directory for relative paths
            max_matches: Maximum number of matches to return
        """
        super().__init__()
        self._work_dir = work_dir
        self._max_matches = max_matches

    def _is_within_work_dir(self, path: Path) -> bool:
        """Check if a path is within the working directory."""
        try:
            path.relative_to(self._work_dir.resolve())
            return True
        except ValueError:
            return False
    async def __call__(self, params: Params) -> ToolResult:
        """Execute the glob search.

        Args:
            params: The search parameters

        Returns:
            ToolResult with matching paths or error
        """
        try:
            # Determine search directory
            if params.directory:
                search_dir = Path(params.directory).expanduser().resolve()
                if not search_dir.is_absolute():
                    return ToolError(
                        message=f"Directory must be an absolute path: {params.directory}",
                    )
                # Security check
                if not self._is_within_work_dir(search_dir):
                    return ToolError(
                        message=(
                            f"Directory `{params.directory}` is outside the working directory. "
                            "You can only search within the working directory."
                        ),
                    )
            else:
                search_dir = self._work_dir

            # Check directory exists
            if not search_dir.exists():
                return ToolError(
                    message=f"Directory `{search_dir}` does not exist.",
                )

            if not search_dir.is_dir():
                return ToolError(
                    message=f"`{search_dir}` is not a directory.",
                )

            # Security check: prevent ** patterns at the root level
            if params.pattern.startswith("**") and not params.directory:
                return ToolError(
                    message=(
                        f"Pattern `{params.pattern}` starts with '**' which is not allowed "
                        "without specifying a directory. This would recursively search all "
                        "directories and may include large directories like `node_modules`. "
                        "Use a more specific pattern or provide a directory."
                    ),
                )

            # Perform glob search
            matches = list(search_dir.glob(params.pattern))

            # Filter directories if not requested
            if not params.include_dirs:
                matches = [p for p in matches if p.is_file()]

            # Sort for consistent output
            matches.sort()

            # Limit matches
            truncated = False
            if len(matches) > self._max_matches:
                matches = matches[: self._max_matches]
                truncated = True

            # Format output (relative to search directory)
            output = "\n".join(str(p.relative_to(search_dir)) for p in matches)

            # Build message
            message = f"Found {len(matches)} matches for pattern `{params.pattern}`."
            if truncated:
                message += f" Only the first {self._max_matches} matches are returned."

            return ToolOk(output=output, message=message)

        except Exception as e:
            return ToolError(
                message=f"Failed to search for pattern `{params.pattern}`. Error: {e}",
            )
