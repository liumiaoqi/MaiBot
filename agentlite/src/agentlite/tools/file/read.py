"""ReadFile tool for AgentLite.

This module provides a tool for reading text files with line numbers.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from agentlite.tool import CallableTool2, ToolError, ToolOk, ToolResult


class Params(BaseModel):
    """Parameters for the ReadFile tool."""

    path: str = Field(
        description=(
            "The path to the file to read. Absolute paths are required when reading files "
            "outside the working directory."
        )
    )
    line_offset: int = Field(
        description=(
            "The line number to start reading from. "
            "By default read from the beginning of the file. "
            "Set this when the file is too large to read at once."
        ),
        default=1,
        ge=1,
    )
    n_lines: int = Field(
        description=(
            "The number of lines to read. "
            "By default read up to max_lines lines. "
            "Set this value when the file is too large to read at once."
        ),
        default=1000,
        ge=1,
    )


class ReadFile(CallableTool2[Params]):
    """Tool for reading text files with line numbers.

    This tool reads a text file and returns its contents with line numbers.
    It supports pagination for large files.

    Example:
        >>> tool = ReadFile(work_dir=Path("/tmp"))
        >>> result = await tool({"path": "/tmp/test.txt"})
    """

    name: str = "ReadFile"
    description: str = (
        "Read a text file from the local filesystem. "
        "Returns the file content with line numbers. "
        "Supports reading specific line ranges for large files."
    )
    params: type[Params] = Params

    def __init__(
        self,
        work_dir: Path,
        max_lines: int = 1000,
        max_line_length: int = 2000,
        max_bytes: int = 100 * 1024,
    ):
        """Initialize the ReadFile tool.

        Args:
            work_dir: The working directory for relative paths
            max_lines: Maximum number of lines to read
            max_line_length: Maximum length of a single line
            max_bytes: Maximum bytes to read from a file
        """
        super().__init__()
        self._work_dir = work_dir
        self._max_lines = max_lines
        self._max_line_length = max_line_length
        self._max_bytes = max_bytes

    def _is_within_work_dir(self, path: Path) -> bool:
        """Check if a path is within the working directory."""
        try:
            path.relative_to(self._work_dir.resolve())
            return True
        except ValueError:
            return False

    async def __call__(self, params: Params) -> ToolResult:
        """Execute the read file operation.

        Args:
            params: The read parameters

        Returns:
            ToolResult with the file content or error
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

            # Security check: if outside work_dir, must be absolute path
            if not self._is_within_work_dir(path) and not Path(params.path).is_absolute():
                return ToolError(
                    message=(
                        f"`{params.path}` is not an absolute path. "
                        "You must provide an absolute path to read a file "
                        "outside the working directory."
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
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except UnicodeDecodeError:
                return ToolError(
                    message=f"`{params.path}` appears to be a binary file and cannot be read as text.",
                )

            # Split into lines
            lines = content.split("\n")

            # Apply line offset
            start_idx = params.line_offset - 1
            if start_idx >= len(lines):
                return ToolOk(
                    output="",
                    message=f"Line offset {params.line_offset} exceeds file length ({len(lines)} lines).",
                )

            # Calculate end index
            end_idx = min(start_idx + params.n_lines, len(lines))
            end_idx = min(end_idx, start_idx + self._max_lines)

            # Extract lines
            selected_lines = lines[start_idx:end_idx]

            # Truncate long lines and count total bytes
            truncated_lines = []
            truncated_line_numbers = []
            total_bytes = 0
            max_bytes_reached = False

            for i, line in enumerate(selected_lines):
                line_num = start_idx + i + 1
                original_line = line

                # Truncate if needed
                if len(line) > self._max_line_length:
                    line = line[: self._max_line_length]
                    truncated_line_numbers.append(line_num)

                # Check bytes limit
                line_bytes = len(line.encode("utf-8"))
                if total_bytes + line_bytes > self._max_bytes:
                    max_bytes_reached = True
                    break

                total_bytes += line_bytes
                truncated_lines.append(line)

            # Format with line numbers
            lines_with_no = []
            for line_num, line in enumerate(truncated_lines, start=start_idx + 1):
                lines_with_no.append(f"{line_num:6d}\t{line}")

            # Build result
            output = "\n".join(lines_with_no)
            message = (
                f"{len(truncated_lines)} lines read from file starting from line {start_idx + 1}."
            )

            if max_bytes_reached:
                message += f" Max {self._max_bytes} bytes reached."
            elif end_idx < len(lines):
                message += f" File has {len(lines)} lines total."

            if truncated_line_numbers:
                message += f" Lines {truncated_line_numbers} were truncated."

            return ToolOk(output=output, message=message)

        except Exception as e:
            return ToolError(
                message=f"Failed to read {params.path}. Error: {e}",
            )
