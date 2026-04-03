"""Grep tool for AgentLite.

This module provides a tool for searching file contents using regex patterns.
"""

from __future__ import annotations
from typing import Optional

import re
from pathlib import Path

from pydantic import BaseModel, Field

from agentlite.tool import CallableTool2, ToolError, ToolOk, ToolResult


class Params(BaseModel):
    """Parameters for the Grep tool."""

    pattern: str = Field(
        description="The regular expression pattern to search for in file contents"
    )
    path: str = Field(
        description=(
            "File or directory to search in. Defaults to current working directory. "
            "If specified, it must be an absolute path."
        ),
        default=".",
    )
    glob: Optional[str] = Field(
        description=(
            "Glob pattern to filter files (e.g. `*.py`, `*.{ts,tsx}`). No filter by default."
        ),
        default=None,
    )
    output_mode: str = Field(
        description=(
            "`content`: Show matching lines (supports `-B`, `-A`, `-C`, `-n`); "
            "`files_with_matches`: Show file paths; "
            "`count_matches`: Show total number of matches. "
            "Defaults to `files_with_matches`."
        ),
        default="files_with_matches",
    )
    before_context: Optional[int] = Field(
        description=(
            "Number of lines to show before each match (the `-B` option). "
            "Requires `output_mode` to be `content`."
        ),
        default=None,
    )
    after_context: Optional[int] = Field(
        description=(
            "Number of lines to show after each match (the `-A` option). "
            "Requires `output_mode` to be `content`."
        ),
        default=None,
    )
    context: Optional[int] = Field(
        description=(
            "Number of lines to show before and after each match (the `-C` option). "
            "Requires `output_mode` to be `content`."
        ),
        default=None,
    )
    line_number: bool = Field(
        description=(
            "Show line numbers in output (the `-n` option). Requires `output_mode` to be `content`."
        ),
        default=False,
    )
    ignore_case: bool = Field(
        description="Case insensitive search (the `-i` option).",
        default=False,
    )


class Grep(CallableTool2[Params]):
    """Tool for searching file contents using regex patterns.

    This tool searches file contents for matches to a regex pattern.
    Supports various output modes and context options.

    Example:
        >>> tool = Grep(work_dir=Path("/tmp"))
        >>> result = await tool({"pattern": "def ", "glob": "*.py"})
    """

    name: str = "Grep"
    description: str = (
        "Search file contents using regular expressions. "
        "Supports various output modes and context options. "
        "Can search individual files or entire directories."
    )
    params: type[Params] = Params

    def __init__(
        self,
        work_dir: Path,
    ):
        """Initialize the Grep tool.

        Args:
            work_dir: The working directory
        """
        super().__init__()
        self._work_dir = work_dir

    def _is_within_work_dir(self, path: Path) -> bool:
        """Check if a path is within the working directory."""
        try:
            path.relative_to(self._work_dir.resolve())
            return True
        except ValueError:
            return False

    def _search_file(
        self,
        file_path: Path,
        pattern: re.Pattern,
        params: Params,
    ) -> list[tuple[int, str]]:
        """Search a single file for matches.

        Args:
            file_path: Path to the file
            pattern: Compiled regex pattern
            params: Search parameters

        Returns:
            List of (line_number, line_content) tuples
        """
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return []

        lines = content.split("\n")
        matches = []

        for i, line in enumerate(lines, 1):
            if pattern.search(line):
                matches.append((i, line))

        return matches

    def _format_matches(
        self,
        matches: dict[Path, list[tuple[int, str]]],
        params: Params,
    ) -> str:
        """Format matches according to output mode.

        Args:
            matches: Dict of file_path -> list of (line_num, line) tuples
            params: Output parameters

        Returns:
            Formatted output string
        """
        if params.output_mode == "files_with_matches":
            return "\n".join(str(p) for p in sorted(matches.keys()))

        if params.output_mode == "count_matches":
            total = sum(len(m) for m in matches.values())
            return f"Total matches: {total}"

        # content mode
        output_lines = []

        for file_path in sorted(matches.keys()):
            file_matches = matches[file_path]

            # Read file for context
            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")
                lines = content.split("\n")
            except Exception:
                continue

            # Determine context lines
            before = params.context if params.context else params.before_context or 0
            after = params.context if params.context else params.after_context or 0

            # Track which lines to include (to avoid duplicates)
            included_lines = set()

            for match_line_num, _ in file_matches:
                start = max(1, match_line_num - before)
                end = min(len(lines), match_line_num + after)

                for i in range(start, end + 1):
                    included_lines.add(i)

            # Build output for this file
            if output_lines:
                output_lines.append("")
            output_lines.append(f"File: {file_path}")

            prev_line = 0
            for line_num in sorted(included_lines):
                # Add separator if there's a gap
                if prev_line and line_num > prev_line + 1:
                    output_lines.append("--")

                line = lines[line_num - 1]
                prefix = f"{line_num}:" if params.line_number else ""
                output_lines.append(f"{prefix}{line}")
                prev_line = line_num

        return "\n".join(output_lines)
    async def __call__(self, params: Params) -> ToolResult:
        """Execute the grep search.

        Args:
            params: The search parameters

        Returns:
            ToolResult with search results or error
        """
        try:
            # Resolve path
            if params.path == ".":
                search_path = self._work_dir
            else:
                search_path = Path(params.path).expanduser().resolve()
                if not search_path.is_absolute():
                    return ToolError(
                        message=f"Path must be an absolute path: {params.path}",
                    )
                # Security check
                if not self._is_within_work_dir(search_path):
                    return ToolError(
                        message=(
                            f"Path `{params.path}` is outside the working directory. "
                            "You can only search within the working directory."
                        ),
                    )

            # Check path exists
            if not search_path.exists():
                return ToolError(
                    message=f"Path `{params.path}` does not exist.",
                )

            # Compile pattern
            flags = re.IGNORECASE if params.ignore_case else 0
            try:
                pattern = re.compile(params.pattern, flags)
            except re.error as e:
                return ToolError(
                    message=f"Invalid regex pattern: {e}",
                )

            # Find files to search
            if search_path.is_file():
                files = [search_path]
            else:
                if params.glob:
                    files = list(search_path.glob(params.glob))
                else:
                    # Default: search all files recursively (with some exclusions)
                    files = [
                        p
                        for p in search_path.rglob("*")
                        if p.is_file()
                        and not any(
                            part.startswith(".") or part in ("node_modules", "__pycache__", ".git")
                            for part in p.parts
                        )
                    ]

                # Filter to text files only
                files = [p for p in files if p.is_file()]

            # Search files
            all_matches: dict[Path, list[tuple[int, str]]] = {}

            for file_path in files:
                matches = self._search_file(file_path, pattern, params)
                if matches:
                    all_matches[file_path] = matches

            # Format output
            output = self._format_matches(all_matches, params)

            # Build message
            total_files = len(all_matches)
            total_matches = sum(len(m) for m in all_matches.values())

            if params.output_mode == "files_with_matches":
                message = f"Found matches in {total_files} file(s)."
            elif params.output_mode == "count_matches":
                message = f"Found {total_matches} total match(es)."
            else:
                message = f"Found {total_matches} match(es) in {total_files} file(s)."

            return ToolOk(output=output, message=message)

        except Exception as e:
            return ToolError(
                message=f"Failed to search. Error: {e}",
            )
