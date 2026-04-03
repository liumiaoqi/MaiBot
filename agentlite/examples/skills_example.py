"""Example demonstrating the skills system for AgentLite.

This example shows how to use skills with an Agent.
"""

import asyncio
from pathlib import Path

from agentlite import Agent, OpenAIProvider
from agentlite.skills import discover_skills, index_skills_by_name, SkillTool


async def main():
    """Run skills example."""

    print("=" * 60)
    print("AgentLite Skills Example")
    print("=" * 60)

    # Discover skills from examples directory
    skills_dir = Path(__file__).parent / "skills"
    skills = discover_skills(skills_dir)

    print(f"\nDiscovered {len(skills)} skill(s):")
    for skill in skills:
        print(f"  - {skill.name}: {skill.description}")
        print(f"    Type: {skill.type}")
        if skill.flow:
            print(f"    Flow nodes: {len(skill.flow.nodes)}")

    # Index skills by name
    skill_index = index_skills_by_name(skills)
    print(f"\nIndexed {len(skill_index)} skill(s)")

    # Create agent (would need API key to actually run)
    print("\n" + "-" * 40)
    print("To use skills with an agent:")
    print("-" * 40)

    code = """
# Create provider
provider = OpenAIProvider(api_key="your-key", model="gpt-4")

# Create agent
agent = Agent(
    provider=provider,
    system_prompt="You are a helpful assistant with access to skills.",
)

# Create skill tool
skill_tool = SkillTool(skill_index, parent_agent=agent)

# Add skill tool to agent
agent.tools.add(skill_tool)

# Now the agent can use skills!
# The agent will see available skills in its context

# Example usage:
response = await agent.run("Review this Python code: def add(a, b): return a + b")
# The agent may choose to use the code-reviewer skill
"""
    print(code)

    print("\n" + "=" * 60)
    print("Key Concepts:")
    print("=" * 60)
    print("1. Skills are defined in SKILL.md files")
    print("2. YAML frontmatter specifies name, description, and type")
    print("3. Standard skills load the markdown as a prompt")
    print("4. Flow skills execute a structured flowchart")
    print("5. Skills are discovered from directories")
    print("6. SkillTool allows agents to execute skills")
    print("\nSkill Format (SKILL.md):")
    print("""  ---
  name: skill-name
  description: When to use this skill...
  type: standard | flow
  ---
  
  # Skill Content
  Instructions for the skill...
  """)


if __name__ == "__main__":
    asyncio.run(main())
