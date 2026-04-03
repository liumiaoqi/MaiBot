"""Skills system for AgentLite.

This module provides a comprehensive skill system similar to kimi-cli,
allowing agents to use modular, reusable skills defined in SKILL.md files.

Skills can be:
- **Standard**: Text-based instructions loaded as prompts
- **Flow**: Structured flowcharts (Mermaid/D2) for deterministic execution

Example:
    >>> from pathlib import Path
    >>> from agentlite.skills import discover_skills, SkillTool
    >>> # Discover skills
    >>> skills = discover_skills(Path("./skills"))
    >>> skill_index = {s.name.lower(): s for s in skills}
    >>> # Create skill tool
    >>> skill_tool = SkillTool(skill_index, parent_agent=agent)
"""

from agentlite.skills.discovery import (
    discover_skills,
    discover_skills_from_roots,
    get_default_skills_dirs,
    index_skills_by_name,
    parse_frontmatter,
    parse_skill_text,
)
from agentlite.skills.flow_parser import (
    FlowParseError,
    parse_d2_flowchart,
    parse_mermaid_flowchart,
)
from agentlite.skills.flow_runner import FlowExecutionError, FlowRunner
from agentlite.skills.models import (
    Flow,
    FlowEdge,
    FlowNode,
    FlowNodeKind,
    Skill,
    SkillType,
    index_skills,
    normalize_skill_name,
)
from agentlite.skills.skill_tool import SkillTool

__all__ = [
    # Models
    "Skill",
    "Flow",
    "FlowNode",
    "FlowEdge",
    "SkillType",
    "FlowNodeKind",
    # Discovery
    "discover_skills",
    "discover_skills_from_roots",
    "get_default_skills_dirs",
    "index_skills",
    "index_skills_by_name",
    "normalize_skill_name",
    "parse_skill_text",
    "parse_frontmatter",
    # Flow parsing
    "parse_mermaid_flowchart",
    "parse_d2_flowchart",
    "FlowParseError",
    # Flow execution
    "FlowRunner",
    "FlowExecutionError",
    # Tool
    "SkillTool",
]
