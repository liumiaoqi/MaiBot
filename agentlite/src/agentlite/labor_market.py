"""Labor Market for managing subagents in AgentLite.

This module provides the LaborMarket class for managing subagents
in a hierarchical agent architecture, similar to kimi-cli's approach.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from agentlite.agent import Agent


class LaborMarket:
    """Manages subagents for a parent agent.

    The LaborMarket acts as a registry for subagents, allowing a parent
    agent to delegate tasks to its children. It supports both fixed
    (pre-defined) and dynamic (runtime-created) subagents.

    This design follows kimi-cli's architecture where:
    - Fixed subagents are defined in configuration and loaded at startup
    - Dynamic subagents can be created at runtime using CreateSubagent tool
    - Subagents can be retrieved by name for task delegation

    Example:
        >>> market = LaborMarket()
        >>> market.add_fixed_subagent("coder", coder_agent, "Writes code")
        >>> market.add_dynamic_subagent("temp", temp_agent)
        >>> agent = market.get_subagent("coder")
    """

    def __init__(self):
        """Initialize an empty labor market."""
        self._fixed_subagents: dict[str, Agent] = {}
        self._fixed_subagent_descs: dict[str, str] = {}
        self._dynamic_subagents: dict[str, Agent] = {}

    @property
    def subagents(self) -> dict[str, Agent]:
        """Get all subagents (both fixed and dynamic).

        Returns:
            Dictionary mapping subagent names to Agent instances.
        """
        return {**self._fixed_subagents, **self._dynamic_subagents}

    @property
    def fixed_subagents(self) -> dict[str, Agent]:
        """Get fixed (pre-defined) subagents.

        Returns:
            Dictionary of fixed subagents.
        """
        return self._fixed_subagents.copy()

    @property
    def dynamic_subagents(self) -> dict[str, Agent]:
        """Get dynamic (runtime-created) subagents.

        Returns:
            Dictionary of dynamic subagents.
        """
        return self._dynamic_subagents.copy()

    @property
    def subagent_descriptions(self) -> dict[str, str]:
        """Get descriptions of all subagents.

        Returns:
            Dictionary mapping subagent names to their descriptions.
            Only fixed subagents have descriptions.
        """
        return self._fixed_subagent_descs.copy()

    def add_fixed_subagent(self, name: str, agent: Agent, description: str) -> None:
        """Add a fixed subagent.

        Fixed subagents are defined in configuration and loaded at startup.
        They typically have their own LaborMarket (for isolation).

        Args:
            name: Unique name for the subagent
            agent: The Agent instance
            description: Description of what the subagent does

        Raises:
            ValueError: If a subagent with the same name already exists.
        """
        if name in self.subagents:
            raise ValueError(f"Subagent '{name}' already exists")

        self._fixed_subagents[name] = agent
        self._fixed_subagent_descs[name] = description

    def add_dynamic_subagent(self, name: str, agent: Agent) -> None:
        """Add a dynamic subagent.

        Dynamic subagents are created at runtime, typically using the
        CreateSubagent tool. They share the parent's LaborMarket.

        Args:
            name: Unique name for the subagent
            agent: The Agent instance

        Raises:
            ValueError: If a subagent with the same name already exists.
        """
        if name in self.subagents:
            raise ValueError(f"Subagent '{name}' already exists")

        self._dynamic_subagents[name] = agent

    def get_subagent(self, name: str) -> Optional[Agent]:
        """Get a subagent by name.

        Args:
            name: Name of the subagent

        Returns:
            The Agent instance if found, None otherwise.
        """
        return self.subagents.get(name)

    def has_subagent(self, name: str) -> bool:
        """Check if a subagent exists.

        Args:
            name: Name of the subagent

        Returns:
            True if the subagent exists, False otherwise.
        """
        return name in self.subagents

    def remove_subagent(self, name: str) -> bool:
        """Remove a subagent.

        Args:
            name: Name of the subagent to remove

        Returns:
            True if the subagent was removed, False if it didn't exist.
        """
        if name in self._fixed_subagents:
            del self._fixed_subagents[name]
            del self._fixed_subagent_descs[name]
            return True

        if name in self._dynamic_subagents:
            del self._dynamic_subagents[name]
            return True

        return False

    def list_subagents(self) -> list[str]:
        """List all subagent names.

        Returns:
            List of subagent names.
        """
        return list(self.subagents.keys())

    def __contains__(self, name: str) -> bool:
        """Check if a subagent exists using 'in' operator."""
        return self.has_subagent(name)

    def __getitem__(self, name: str) -> Agent:
        """Get a subagent using bracket notation."""
        agent = self.get_subagent(name)
        if agent is None:
            raise KeyError(f"Subagent '{name}' not found")
        return agent

    def __iter__(self):
        """Iterate over subagent names."""
        return iter(self.subagents)

    def __len__(self) -> int:
        """Get the number of subagents."""
        return len(self.subagents)
