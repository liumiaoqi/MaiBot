"""Tool suite for AgentLite - A collection of tools inspired by kimi-cli.

This module provides a comprehensive set of tools for file operations,
shell execution, web access, and more, with configuration support
for enabling/disabling individual tools.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from agentlite.tool import CallableTool2, ToolOk, ToolError, ToolResult, SimpleToolset
from agentlite.tools.config import (
    ToolSuiteConfig,
    FileToolsConfig,
    ShellToolsConfig,
    WebToolsConfig,
    MultiAgentToolsConfig,
    ToolGroupConfig,
)

# Import tool implementations
from agentlite.tools.file.read import ReadFile
from agentlite.tools.file.write import WriteFile
from agentlite.tools.file.replace import StrReplaceFile
from agentlite.tools.file.glob import Glob
from agentlite.tools.file.grep import Grep
from agentlite.tools.file.read_media import ReadMediaFile
from agentlite.tools.shell.shell import Shell
from agentlite.tools.web.fetch import FetchURL
from agentlite.tools.misc.todo import SetTodoList
from agentlite.tools.misc.think import Think


class ConfigurableToolset(SimpleToolset):
    """A toolset that supports configuration-based tool enabling/disabling.

    This toolset loads tools based on a ToolSuiteConfig, only adding
    tools that are enabled in the configuration.

    Example:
        >>> config = ToolSuiteConfig(
        ...     file_tools=FileToolsConfig(
        ...         tools={"WriteFile": False}  # Disable WriteFile
        ...     )
        ... )
        >>> toolset = ConfigurableToolset(config)
        >>> "ReadFile" in toolset  # True
        True
        >>> "WriteFile" in toolset  # False
        False
    """

    def __init__(self, config: ToolSuiteConfig | None = None, work_dir: Optional[str] = None):
        """Initialize the configurable toolset.

        Args:
            config: Tool suite configuration. If None, uses default config (all enabled).
            work_dir: Working directory for file operations. Defaults to current directory.
        """
        super().__init__()

        self.config = config or ToolSuiteConfig()
        self.work_dir = Path(work_dir) if work_dir else Path.cwd()

        self._load_tools()

    def _load_tools(self) -> None:
        """Load tools based on configuration."""
        enabled = self.config.get_enabled_tools()

        # File tools
        if "file" in enabled:
            self._load_file_tools(enabled["file"])

        # Shell tools
        if "shell" in enabled:
            self._load_shell_tools(enabled["shell"])

        # Web tools
        if "web" in enabled:
            self._load_web_tools(enabled["web"])

        # Multi-agent tools
        if "multiagent" in enabled:
            self._load_multiagent_tools(enabled["multiagent"])

        # Misc tools
        if "misc" in enabled:
            self._load_misc_tools(enabled["misc"])

    def _load_file_tools(self, tool_names: list[str]) -> None:
        """Load file operation tools."""
        cfg = self.config.file_tools

        if "ReadFile" in tool_names:
            self.add(
                ReadFile(
                    work_dir=self.work_dir,
                    max_lines=cfg.max_lines,
                    max_line_length=cfg.max_line_length,
                    max_bytes=cfg.max_bytes,
                )
            )

        if "WriteFile" in tool_names:
            self.add(
                WriteFile(
                    work_dir=self.work_dir, allow_outside_work_dir=cfg.allow_write_outside_work_dir
                )
            )

        if "StrReplaceFile" in tool_names:
            self.add(
                StrReplaceFile(
                    work_dir=self.work_dir, allow_outside_work_dir=cfg.allow_write_outside_work_dir
                )
            )

        if "Glob" in tool_names:
            self.add(Glob(work_dir=self.work_dir, max_matches=cfg.max_glob_matches))

        if "Grep" in tool_names:
            self.add(Grep(work_dir=self.work_dir))

        if "ReadMediaFile" in tool_names:
            self.add(ReadMediaFile(work_dir=self.work_dir))

    def _load_shell_tools(self, tool_names: list[str]) -> None:
        """Load shell execution tools."""
        cfg = self.config.shell_tools

        if "Shell" in tool_names:
            self.add(
                Shell(
                    timeout=cfg.timeout,
                    max_timeout=cfg.max_timeout,
                    blocked_commands=cfg.blocked_commands,
                )
            )

    def _load_web_tools(self, tool_names: list[str]) -> None:
        """Load web-related tools."""
        cfg = self.config.web_tools

        if "FetchURL" in tool_names:
            self.add(
                FetchURL(
                    timeout=cfg.timeout,
                    user_agent=cfg.user_agent,
                    max_content_length=cfg.max_content_length,
                )
            )

    def _load_multiagent_tools(self, tool_names: list[str]) -> None:
        """Load multi-agent tools."""
        # Multi-agent tools are intentionally disabled in this submodule
        # because nested subagents are not supported in subagent runtime.
        return

    def _load_misc_tools(self, tool_names: list[str]) -> None:
        """Load miscellaneous tools."""
        if "SetTodoList" in tool_names:
            self.add(SetTodoList())

        if "Think" in tool_names:
            self.add(Think())

    def reload(self, config: ToolSuiteConfig | None = None) -> None:
        """Reload tools with a new configuration.

        Args:
            config: New configuration. If None, reloads with current config.
        """
        if config:
            self.config = config

        # Clear existing tools
        self._tools.clear()

        # Reload
        self._load_tools()


# Convenience exports
__all__ = [
    # Toolset
    "ConfigurableToolset",
    # Config classes
    "ToolSuiteConfig",
    "FileToolsConfig",
    "ShellToolsConfig",
    "WebToolsConfig",
    "MultiAgentToolsConfig",
    "ToolGroupConfig",
    # Tools
    "ReadFile",
    "WriteFile",
    "StrReplaceFile",
    "Glob",
    "Grep",
    "ReadMediaFile",
    "Shell",
    "FetchURL",
    "SetTodoList",
    "Think",
]
