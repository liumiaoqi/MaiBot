"""Skill system for AgentLite.

This module provides a skill system similar to kimi-cli, allowing agents
to use modular, reusable skills defined in SKILL.md files.

Skills can be:
- Standard: Text-based instructions loaded as prompts
- Flow: Structured flowcharts (Mermaid/D2) for deterministic execution

Example:
    >>> from agentlite.skills import Skill, discover_skills
    >>> skills = discover_skills(Path("./skills"))
    >>> for skill in skills:
    ...     print(f"{skill.name}: {skill.description}")
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field

SkillType = Literal["standard", "flow"]
FlowNodeKind = Literal["begin", "end", "task", "decision"]


class FlowNode(BaseModel):
    """A node in a flowchart.

    Attributes:
        id: Unique identifier for the node
        label: Display text or content for the node
        kind: Type of node (begin, end, task, decision)
    """

    id: str = Field(description="Unique node identifier")
    label: str = Field(description="Node display text")
    kind: FlowNodeKind = Field(description="Node type")


class FlowEdge(BaseModel):
    """An edge connecting two nodes in a flowchart.

    Attributes:
        src: Source node ID
        dst: Destination node ID
        label: Optional label for the edge (used for decision branches)
    """

    src: str = Field(description="Source node ID")
    dst: str = Field(description="Destination node ID")
    label: Optional[str] = Field(default=None, description="Edge label for decisions")


class Flow(BaseModel):
    """A flowchart defining a structured workflow.

    Flow skills use flowcharts to define deterministic, step-by-step
    workflows that the agent executes node by node.

    Attributes:
        nodes: Dictionary mapping node IDs to FlowNode objects
        outgoing: Dictionary mapping node IDs to their outgoing edges
        begin_id: ID of the start node
        end_id: ID of the end node
    """

    nodes: dict[str, FlowNode] = Field(description="Node ID to node mapping")
    outgoing: dict[str, list[FlowEdge]] = Field(description="Node outgoing edges")
    begin_id: str = Field(description="Start node ID")
    end_id: str = Field(description="End node ID")


class Skill(BaseModel):
    """A skill definition for AgentLite.

    Skills are modular, reusable capabilities defined in SKILL.md files.
    They can be standard (text-based) or flow-based (structured workflows).

    Attributes:
        name: Unique skill name
        description: When and what the skill does (used for triggering)
        type: Skill type - "standard" or "flow"
        dir: Directory containing the skill files
        flow: Flow definition (only for flow-type skills)

    Example SKILL.md:
        ---
        name: code-reviewer
        description: Review code for bugs, style issues, and best practices
        type: standard
        ---

        # Code Reviewer

        When reviewing code:
        1. Check for syntax errors
        2. Verify style guidelines
        3. Suggest improvements
    """

    name: str = Field(description="Unique skill name")
    description: str = Field(description="Skill description and triggering criteria")
    type: SkillType = Field(default="standard", description="Skill type")
    dir: Path = Field(description="Skill directory path")
    flow: Optional[Flow] = Field(default=None, description="Flow definition for flow-type skills")

    @property
    def skill_md_file(self) -> Path:
        """Path to the SKILL.md file."""
        return self.dir / "SKILL.md"

    def read_content(self) -> str:
        """Read the full SKILL.md content.

        Returns:
            The content of the SKILL.md file

        Raises:
            FileNotFoundError: If SKILL.md doesn't exist
        """
        return self.skill_md_file.read_text(encoding="utf-8").strip()


def normalize_skill_name(name: str) -> str:
    """Normalize a skill name for lookup.

    Args:
        name: The skill name to normalize

    Returns:
        Lowercase version of the name for case-insensitive lookup
    """
    return name.casefold()


def index_skills(skills: Iterable[Skill]) -> dict[str, Skill]:
    """Build a lookup table for skills by normalized name.

    Args:
        skills: Iterable of Skill objects

    Returns:
        Dictionary mapping normalized names to Skill objects

    Example:
        >>> skills = [Skill(name="CodeReview", ...), Skill(name="TestWriter", ...)]
        >>> index = index_skills(skills)
        >>> index["codereview"].name
        "CodeReview"
    """
    return {normalize_skill_name(skill.name): skill for skill in skills}
