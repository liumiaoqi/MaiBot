"""Skill tool for AgentLite.

This module provides a tool for executing skills within an agent.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from agentlite.tool import CallableTool2, ToolError, ToolOk, ToolResult

if TYPE_CHECKING:
    from agentlite.agent import Agent
    from agentlite.skills.models import Skill


class SkillParams(BaseModel):
    """Parameters for executing a skill."""

    skill_name: str = Field(description="Name of the skill to execute")
    args: str = Field(default="", description="Additional arguments or context for the skill")


class SkillTool(CallableTool2[SkillParams]):
    """Tool for executing skills.

    This tool allows an agent to execute skills from its skill registry.
    Skills can be standard (text-based) or flow-based (structured workflows).

    Example:
        >>> from agentlite.skills.discovery import discover_skills
        >>> from agentlite.skills.models import index_skills
        >>> # Discover and index skills
        >>> skills = discover_skills(Path("./skills"))
        >>> skill_index = index_skills(skills)
        >>> # Create skill tool
        >>> skill_tool = SkillTool(skill_index, parent_agent=agent)
        >>> # Execute a skill
        >>> result = await skill_tool(
        ...     {"skill_name": "code-review", "args": "Review this Python function..."}
        ... )
    """

    name: str = "Skill"
    description: str = (
        "Execute a predefined skill. "
        "Skills provide specialized workflows and domain knowledge. "
        "Available skills are shown in the system context."
    )
    params: type[SkillParams] = SkillParams

    def __init__(
        self,
        skills: dict[str, "Skill"],
        parent_agent: "Agent" | None = None,
    ):
        """Initialize the skill tool.

        Args:
            skills: Dictionary mapping normalized skill names to Skill objects
            parent_agent: The parent agent (used for executing skills)
        """
        super().__init__()
        self._skills = skills
        self._parent_agent = parent_agent

    async def __call__(self, params: SkillParams) -> ToolResult:
        """Execute a skill.

        Args:
            params: Skill execution parameters

        Returns:
            ToolResult with the skill output or error
        """
        from agentlite.skills.models import normalize_skill_name

        if not params.skill_name:
            return ToolError(message="Skill name cannot be empty")

        # Find the skill
        normalized_name = normalize_skill_name(params.skill_name)
        skill = self._skills.get(normalized_name)

        if skill is None:
            available = ", ".join(sorted(self._skills.keys()))
            return ToolError(
                message=f"Skill '{params.skill_name}' not found. Available: {available or 'none'}"
            )

        try:
            # Execute based on skill type
            if skill.type == "flow" and skill.flow is not None:
                return await self._execute_flow_skill(skill, params.args)
            else:
                return await self._execute_standard_skill(skill, params.args)

        except Exception as e:
            return ToolError(message=f"Skill execution failed: {e}")

    async def _execute_standard_skill(self, skill: "Skill", args: str) -> ToolResult:
        """Execute a standard (text-based) skill.

        Loads the SKILL.md content and uses it as a prompt for the agent.

        Args:
            skill: The skill to execute
            args: Additional arguments from the user

        Returns:
            ToolResult with the skill output
        """
        # Read skill content
        content = skill.read_content()

        # Parse frontmatter to get just the body
        from agentlite.skills.discovery import parse_frontmatter

        frontmatter = parse_frontmatter(content)

        # Extract body (remove frontmatter if present)
        if frontmatter and content.startswith("---"):
            end_idx = content.find("\n---", 3)
            if end_idx != -1:
                body = content[end_idx + 4 :].strip()
            else:
                body = content
        else:
            body = content

        # Append user arguments if provided
        if args.strip():
            body = f"{body}\n\nUser request: {args.strip()}"

        # Execute using parent agent if available
        if self._parent_agent is not None:
            # Create a temporary message with the skill content
            response = await self._parent_agent.run(body)
            return ToolOk(output=response, message=f"Skill '{skill.name}' executed successfully")
        else:
            # Return the skill content for the LLM to use
            return ToolOk(
                output=body, message=f"Skill '{skill.name}' loaded (no parent agent to execute)"
            )

    async def _execute_flow_skill(self, skill: "Skill", args: str) -> ToolResult:
        """Execute a flow-based skill.

        Executes the flowchart node by node.

        Args:
            skill: The flow skill to execute
            args: Additional arguments from the user

        Returns:
            ToolResult with the flow output
        """
        from agentlite.skills.flow_runner import FlowRunner

        if skill.flow is None:
            return ToolError(message=f"Flow skill '{skill.name}' has no flow definition")

        if self._parent_agent is None:
            return ToolError(message="Flow skills require a parent agent to execute")

        # Create flow runner and execute
        runner = FlowRunner(skill.flow, skill.name)

        try:
            output = await runner.run(self._parent_agent, args)
            return ToolOk(
                output=output, message=f"Flow skill '{skill.name}' completed successfully"
            )
        except Exception as e:
            return ToolError(message=f"Flow execution failed: {e}")
