"""Tool group configuration system for AgentLite.

This module provides configuration management for tool groups,
allowing users to enable/disable specific tools.
"""

from __future__ import annotations


from pydantic import BaseModel, Field


class ToolGroupConfig(BaseModel):
    """Configuration for a group of tools.

    This configuration allows users to enable or disable specific tools
    within the tool group. All tools are enabled by default.

    Example:
        >>> config = ToolGroupConfig(
        ...     enabled=True,
        ...     tools={
        ...         "ReadFile": True,
        ...         "WriteFile": False,  # Disabled
        ...     },
        ... )
    """

    enabled: bool = Field(default=True, description="Whether the entire tool group is enabled")

    tools: dict[str, bool] = Field(
        default_factory=dict,
        description="Individual tool enable/disable settings. True=enabled, False=disabled. "
        "Tools not listed here follow the default behavior (enabled).",
    )

    default_tool_enabled: bool = Field(
        default=True, description="Default state for tools not explicitly listed in 'tools' dict"
    )

    def is_tool_enabled(self, tool_name: str) -> bool:
        """Check if a specific tool is enabled.

        Args:
            tool_name: The name of the tool to check

        Returns:
            True if the tool is enabled, False otherwise
        """
        if not self.enabled:
            return False

        # Check explicit setting
        if tool_name in self.tools:
            return self.tools[tool_name]

        # Use default
        return self.default_tool_enabled

    def enable_tool(self, tool_name: str) -> None:
        """Enable a specific tool.

        Args:
            tool_name: The name of the tool to enable
        """
        self.tools[tool_name] = True

    def disable_tool(self, tool_name: str) -> None:
        """Disable a specific tool.

        Args:
            tool_name: The name of the tool to disable
        """
        self.tools[tool_name] = False

    def set_tool_state(self, tool_name: str, enabled: bool) -> None:
        """Set the enabled state of a specific tool.

        Args:
            tool_name: The name of the tool
            enabled: True to enable, False to disable
        """
        self.tools[tool_name] = enabled


class FileToolsConfig(ToolGroupConfig):
    """Configuration for file operation tools."""

    max_lines: int = Field(
        default=1000, description="Maximum number of lines to read from a file", ge=1, le=10000
    )

    max_line_length: int = Field(
        default=2000, description="Maximum length of a single line", ge=100, le=10000
    )

    max_bytes: int = Field(
        default=100 * 1024,  # 100KB
        description="Maximum bytes to read from a file",
        ge=1024,
        le=10 * 1024 * 1024,  # 10MB
    )

    allow_write_outside_work_dir: bool = Field(
        default=False, description="Allow writing files outside the working directory"
    )

    max_glob_matches: int = Field(
        default=1000, description="Maximum number of glob matches to return", ge=1, le=10000
    )


class ShellToolsConfig(ToolGroupConfig):
    """Configuration for shell execution tools."""

    timeout: int = Field(
        default=60, description="Default timeout for shell commands in seconds", ge=1, le=3600
    )

    max_timeout: int = Field(
        default=300, description="Maximum allowed timeout for shell commands", ge=1, le=3600
    )

    blocked_commands: list[str] = Field(
        default_factory=list, description="List of command patterns to block"
    )


class WebToolsConfig(ToolGroupConfig):
    """Configuration for web-related tools."""

    timeout: int = Field(
        default=30, description="Timeout for HTTP requests in seconds", ge=1, le=300
    )

    user_agent: str = Field(
        default="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        description="User-Agent string for HTTP requests",
    )

    max_content_length: int = Field(
        default=1024 * 1024,  # 1MB
        description="Maximum content length to fetch",
        ge=1024,
        le=10 * 1024 * 1024,  # 10MB
    )


class MultiAgentToolsConfig(ToolGroupConfig):
    """Configuration for multi-agent tools."""

    enabled: bool = Field(
        default=False, description="Whether multi-agent tools are enabled. Disabled by default for subagent mode."
    )

    max_steps: int = Field(
        default=50, description="Maximum steps for subagent execution", ge=1, le=1000
    )

    inherit_context: bool = Field(
        default=False, description="Whether subagents inherit parent context"
    )


class ToolSuiteConfig(BaseModel):
    """Complete configuration for all tool groups.

    This is the main configuration class that aggregates all tool group configs.

    Example:
        >>> config = ToolSuiteConfig(
        ...     file_tools=FileToolsConfig(tools={"WriteFile": False}),
        ...     shell_tools=ShellToolsConfig(
        ...         enabled=False  # Disable all shell tools
        ...     ),
        ... )
    """

    file_tools: FileToolsConfig = Field(
        default_factory=FileToolsConfig, description="File operation tools configuration"
    )

    shell_tools: ShellToolsConfig = Field(
        default_factory=ShellToolsConfig, description="Shell execution tools configuration"
    )

    web_tools: WebToolsConfig = Field(
        default_factory=WebToolsConfig, description="Web-related tools configuration"
    )

    multiagent_tools: MultiAgentToolsConfig = Field(
        default_factory=MultiAgentToolsConfig, description="Multi-agent tools configuration"
    )

    misc_tools: ToolGroupConfig = Field(
        default_factory=ToolGroupConfig,
        description="Miscellaneous tools (todo, think, etc.) configuration",
    )

    def get_enabled_tools(self) -> dict[str, list[str]]:
        """Get a mapping of tool group names to their enabled tools.

        Returns:
            Dictionary mapping tool group names to lists of enabled tool names
        """
        result: dict[str, list[str]] = {}

        # File tools
        if self.file_tools.enabled:
            file_tools = [
                "ReadFile",
                "WriteFile",
                "StrReplaceFile",
                "Glob",
                "Grep",
                "ReadMediaFile",
            ]
            result["file"] = [t for t in file_tools if self.file_tools.is_tool_enabled(t)]

        # Shell tools
        if self.shell_tools.enabled:
            shell_tools = ["Shell"]
            result["shell"] = [t for t in shell_tools if self.shell_tools.is_tool_enabled(t)]

        # Web tools
        if self.web_tools.enabled:
            web_tools = ["FetchURL"]
            result["web"] = [t for t in web_tools if self.web_tools.is_tool_enabled(t)]

        # Multi-agent tools
        if self.multiagent_tools.enabled:
            multi_tools = ["Task", "CreateSubagent"]
            result["multiagent"] = [
                t for t in multi_tools if self.multiagent_tools.is_tool_enabled(t)
            ]

        # Misc tools
        if self.misc_tools.enabled:
            misc_tools = ["SetTodoList", "Think"]
            result["misc"] = [t for t in misc_tools if self.misc_tools.is_tool_enabled(t)]

        return result
