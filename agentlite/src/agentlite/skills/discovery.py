"""Skill discovery and loading utilities for AgentLite.

This module provides functions for discovering and loading skills from
directory structures, similar to kimi-cli's skill system.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING, Dict, Optional

import yaml

if TYPE_CHECKING:
    from agentlite.skills.models import Flow, Skill


def parse_frontmatter(content: str) -> Optional[Dict]:
    """Parse YAML frontmatter from markdown content.

    Args:
        content: The file content that may contain frontmatter

    Returns:
        Dictionary of frontmatter data, or None if no frontmatter found

    Example:
        >>> content = '''---
        ... name: my-skill
        ... description: Does something useful
        ... ---
        ... # Skill Content
        ... '''
        >>> parse_frontmatter(content)
        {'name': 'my-skill', 'description': 'Does something useful'}
    """
    if not content.startswith("---"):
        return None

    try:
        # Find the end of frontmatter
        end_idx = content.find("\n---", 3)
        if end_idx == -1:
            return None

        # Extract and parse YAML
        frontmatter_text = content[3:end_idx].strip()
        return yaml.safe_load(frontmatter_text) or {}
    except Exception:
        return None


def parse_flow_from_skill(content: str) -> "Flow":
    """Parse a flowchart from skill content.

    Looks for mermaid or d2 code blocks and parses them into Flow objects.

    Args:
        content: The SKILL.md content containing a flowchart

    Returns:
        Parsed Flow object

    Raises:
        ValueError: If no valid flowchart found
    """
    from agentlite.skills.flow_parser import (
        FlowParseError,
        parse_d2_flowchart,
        parse_mermaid_flowchart,
    )

    # Extract code blocks
    code_blocks = _extract_code_blocks(content)

    for lang, code in code_blocks:
        try:
            if lang == "mermaid":
                return parse_mermaid_flowchart(code)
            elif lang == "d2":
                return parse_d2_flowchart(code)
        except FlowParseError:
            continue

    raise ValueError("No valid mermaid or d2 flowchart found in skill content")


def _extract_code_blocks(content: str) -> list[tuple[str, str]]:
    """Extract fenced code blocks from markdown content.

    Args:
        content: Markdown content

    Returns:
        List of (language, code) tuples
    """
    blocks = []
    in_block = False
    current_lang = ""
    current_code = []
    fence_char = ""
    fence_len = 0

    for line in content.split("\n"):
        stripped = line.lstrip()

        if not in_block:
            # Check for fence start
            if stripped.startswith("```") or stripped.startswith("~~~"):
                fence_char = stripped[0]
                fence_len = len(stripped) - len(stripped.lstrip(fence_char))
                if fence_len >= 3:
                    # Extract language
                    info = stripped[fence_len:].strip()
                    current_lang = info.split()[0] if info else ""
                    in_block = True
                    current_code = []
        else:
            # Check for fence end
            if stripped.startswith(fence_char * fence_len):
                blocks.append((current_lang, "\n".join(current_code)))
                in_block = False
                current_lang = ""
                current_code = []
            else:
                current_code.append(line)

    return blocks


def parse_skill_text(content: str, dir_path: Path) -> "Skill":
    """Parse skill content into a Skill object.

    Args:
        content: The SKILL.md content
        dir_path: Path to the skill directory

    Returns:
        Parsed Skill object

    Raises:
        ValueError: If the skill content is invalid
    """
    from agentlite.skills.flow_parser import FlowParseError
    from agentlite.skills.models import Skill

    frontmatter = parse_frontmatter(content) or {}

    name = frontmatter.get("name") or dir_path.name
    description = frontmatter.get("description") or "No description provided."
    skill_type = frontmatter.get("type") or "standard"

    if skill_type not in ("standard", "flow"):
        raise ValueError(f'Invalid skill type "{skill_type}"')

    # Parse flow if this is a flow-type skill
    flow = None
    if skill_type == "flow":
        try:
            flow = parse_flow_from_skill(content)
        except (ValueError, FlowParseError) as e:
            # Log warning and fall back to standard
            import logging

            logging.warning(
                f"Failed to parse flow skill '{name}': {e}. Treating as standard skill."
            )
            skill_type = "standard"
            flow = None

    return Skill(
        name=name,
        description=description,
        type=skill_type,
        dir=dir_path,
        flow=flow,
    )


def discover_skills(skills_dir: Path) -> list["Skill"]:
    """Discover all skills in a directory.

    Scans the directory for subdirectories containing SKILL.md files
    and parses them into Skill objects.

    Args:
        skills_dir: Directory to scan for skills

    Returns:
        List of discovered Skill objects, sorted by name

    Example:
        >>> skills = discover_skills(Path("./skills"))
        >>> for skill in skills:
        ...     print(f"{skill.name}: {skill.description}")
    """
    from agentlite.skills.models import Skill

    if not skills_dir.is_dir():
        return []

    skills: list[Skill] = []

    for skill_dir in skills_dir.iterdir():
        if not skill_dir.is_dir():
            continue

        skill_md = skill_dir / "SKILL.md"
        if not skill_md.is_file():
            continue

        try:
            content = skill_md.read_text(encoding="utf-8")
            skills.append(parse_skill_text(content, skill_dir))
        except Exception as e:
            import logging

            logging.warning(f"Failed to parse skill at {skill_md}: {e}")
            continue

    return sorted(skills, key=lambda s: s.name)


def discover_skills_from_roots(skills_dirs: Iterable[Path]) -> list["Skill"]:
    """Discover skills from multiple directory roots.

    Skills from later directories will override skills with the same name
    from earlier directories.

    Args:
        skills_dirs: Iterable of directories to scan

    Returns:
        List of unique Skill objects, sorted by name

    Example:
        >>> roots = [Path("./builtin"), Path("~/.config/skills").expanduser()]
        >>> skills = discover_skills_from_roots(roots)
    """
    from agentlite.skills.models import normalize_skill_name

    skills_by_name: dict[str, "Skill"] = {}

    for skills_dir in skills_dirs:
        for skill in discover_skills(skills_dir):
            # Later skills override earlier ones with same name
            skills_by_name[normalize_skill_name(skill.name)] = skill

    return sorted(skills_by_name.values(), key=lambda s: s.name)


def get_default_skills_dirs(work_dir: Path | None = None) -> list[Path]:
    """Get the default skill directory search paths.

    Returns directories in priority order:
    1. User-level: ~/.config/agents/skills/ (or alternatives)
    2. Project-level: ./.agents/skills/ (or alternatives)

    Args:
        work_dir: Working directory for project-level search (default: current dir)

    Returns:
        List of existing skill directories
    """
    dirs: list[Path] = []

    # User-level candidates
    user_candidates = [
        Path.home() / ".config" / "agents" / "skills",
        Path.home() / ".agents" / "skills",
        Path.home() / ".kimi" / "skills",
    ]

    for candidate in user_candidates:
        if candidate.is_dir():
            dirs.append(candidate)
            break  # Only use first existing

    # Project-level candidates
    if work_dir is None:
        work_dir = Path.cwd()

    project_candidates = [
        work_dir / ".agents" / "skills",
        work_dir / ".kimi" / "skills",
    ]

    for candidate in project_candidates:
        if candidate.is_dir():
            dirs.append(candidate)
            break  # Only use first existing

    return dirs


def index_skills_by_name(skills: Iterable["Skill"]) -> dict[str, "Skill"]:
    """Build a lookup table for skills by normalized name.

    Args:
        skills: Iterable of Skill objects

    Returns:
        Dictionary mapping normalized names to Skill objects
    """
    from agentlite.skills.models import normalize_skill_name

    return {normalize_skill_name(skill.name): skill for skill in skills}
