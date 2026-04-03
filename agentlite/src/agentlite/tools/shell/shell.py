"""Shell tool for AgentLite.

This module provides a tool for executing shell commands.
"""

from __future__ import annotations
from typing import Optional

import asyncio
import platform

from pydantic import BaseModel, Field

from agentlite.tool import CallableTool2, ToolError, ToolOk, ToolResult


class Params(BaseModel):
    """Parameters for the Shell tool."""

    command: str = Field(description="The shell command to execute.")
    timeout: int = Field(
        description=(
            "The timeout in seconds for the command to execute. "
            "If the command takes longer than this, it will be killed."
        ),
        default=60,
        ge=1,
        le=3600,
    )


class Shell(CallableTool2[Params]):
    """Tool for executing shell commands.

    This tool executes shell commands and returns their output.
    Supports configurable timeout and command blocking for security.

    Example:
        >>> tool = Shell()
        >>> result = await tool({"command": "ls -la"})
    """

    name: str = "Shell"
    description: str = (
        "Execute a shell command and return its output. "
        "Supports bash on Unix/Linux/macOS and PowerShell on Windows. "
        "Use with caution - commands are executed with user permissions."
    )
    params: type[Params] = Params

    def __init__(
        self,
        timeout: int = 60,
        max_timeout: int = 300,
        blocked_commands: Optional[list[str]] = None,
    ):
        """Initialize the Shell tool.

        Args:
            timeout: Default timeout in seconds
            max_timeout: Maximum allowed timeout
            blocked_commands: List of command patterns to block
        """
        super().__init__()
        self._default_timeout = timeout
        self._max_timeout = max_timeout
        self._blocked_commands = blocked_commands or []
        self._is_windows = platform.system() == "Windows"

    def _is_blocked(self, command: str) -> Optional[str]:
        """Check if a command is blocked.

        Args:
            command: The command to check

        Returns:
            Block reason if blocked, None otherwise
        """
        cmd_lower = command.lower().strip()

        for blocked in self._blocked_commands:
            if blocked.lower() in cmd_lower:
                return f"Command contains blocked pattern: {blocked}"

        return None
    async def __call__(self, params: Params) -> ToolResult:
        """Execute the shell command.

        Args:
            params: The command parameters

        Returns:
            ToolResult with command output or error
        """
        if not params.command:
            return ToolError(
                message="Command cannot be empty.",
            )

        # Check if blocked
        if block_reason := self._is_blocked(params.command):
            return ToolError(
                message=f"Command blocked: {block_reason}",
            )

        # Validate timeout
        timeout = min(params.timeout, self._max_timeout)

        try:
            # Determine shell
            if self._is_windows:
                # Use PowerShell on Windows
                shell_cmd = ["powershell", "-Command", params.command]
            else:
                # Use bash on Unix/Linux/macOS
                shell_cmd = ["bash", "-c", params.command]

            # Execute command
            process = await asyncio.create_subprocess_exec(
                *shell_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return ToolError(
                    message=f"Command timed out after {timeout} seconds.",
                )

            # Decode output
            stdout_str = stdout.decode("utf-8", errors="replace")
            stderr_str = stderr.decode("utf-8", errors="replace")

            # Build output
            output_parts = []
            if stdout_str:
                output_parts.append(stdout_str)
            if stderr_str:
                output_parts.append(f"[stderr]\n{stderr_str}")

            output = "\n".join(output_parts)

            if process.returncode == 0:
                return ToolOk(
                    output=output,
                    message="Command executed successfully (exit code 0).",
                )
            else:
                return ToolError(
                    message=f"Command failed with exit code {process.returncode}.",
                    output=output,
                )

        except Exception as e:
            return ToolError(
                message=f"Failed to execute command. Error: {e}",
            )
