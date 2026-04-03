"""Subagent configuration models for AgentLite.

This module provides configuration models for defining subagents
in a hierarchical agent architecture.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, model_validator


class SubagentConfig(BaseModel):
    """Configuration for a subagent.

    Subagents are child agents that can be called by a parent agent
    using the Task tool. Each subagent has its own system prompt
    and can optionally have its own tools.

    Attributes:
        name: Unique name for the subagent
        description: Description of what the subagent does
        system_prompt: System prompt for the subagent
        system_prompt_path: Path to a file containing the system prompt
        tools: List of tool paths to load (inherits from parent if not specified)
        exclude_tools: Tools to exclude from parent inheritance
        subagents: Nested subagents (for hierarchical structure)
        max_iterations: Maximum tool call iterations for this subagent

    Example:
        >>> config = SubagentConfig(
        ...     name="coder",
        ...     description="Good at writing code",
        ...     system_prompt="You are a coding assistant.",
        ...     exclude_tools=["Task", "CreateSubagent"],
        ... )
    """

    name: str = Field(description="Unique name for the subagent")
    description: str = Field(description="Description of what the subagent does")
    system_prompt: Optional[str] = Field(default=None, description="System prompt for the subagent")
    system_prompt_path: Optional[Path] = Field(
        default=None, description="Path to a file containing the system prompt"
    )
    tools: Optional[list[str]] = Field(
        default=None,
        description="List of tool import paths (e.g., 'agentlite.tools.file:ReadFile')",
    )
    exclude_tools: list[str] = Field(
        default_factory=list, description="Tool names to exclude from parent inheritance"
    )
    subagents: list[SubagentConfig] = Field(
        default_factory=list, description="Nested subagents (hierarchical structure)"
    )
    max_iterations: int = Field(
        default=80, description="Maximum tool call iterations", ge=1, le=100
    )

    @model_validator(mode="after")
    def validate_system_prompt(self) -> SubagentConfig:
        """Validate that either system_prompt or system_prompt_path is provided."""
        if self.system_prompt is None and self.system_prompt_path is None:
            raise ValueError("Either system_prompt or system_prompt_path must be provided")
        return self

    def get_system_prompt(self) -> str:
        """Get the system prompt text.

        Returns:
            The system prompt string.

        Raises:
            FileNotFoundError: If system_prompt_path is specified but file doesn't exist.
        """
        if self.system_prompt is not None:
            return self.system_prompt

        if self.system_prompt_path is not None:
            return Path(self.system_prompt_path).read_text(encoding="utf-8").strip()

        raise ValueError("No system prompt available")


class SubagentSpec(BaseModel):
    """Specification for loading a subagent from a file.

    This is used when subagents are defined in separate YAML files,
    similar to kimi-cli's approach.

    Attributes:
        path: Path to the subagent configuration file
        description: Description of the subagent
    """

    path: Path = Field(description="Path to subagent config file")
    description: str = Field(description="Description of the subagent")

    def load(self) -> SubagentConfig:
        """Load the subagent configuration from the file.

        Returns:
            The loaded SubagentConfig.
        """
        import yaml

        with open(self.path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        return SubagentConfig(**data)
