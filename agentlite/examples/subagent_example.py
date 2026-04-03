"""Example demonstrating subagent usage in AgentLite.

This example shows how to create a parent agent with subagents
and delegate tasks to them using the Task tool.
"""

import asyncio

from agentlite import Agent, OpenAIProvider
from agentlite.labor_market import LaborMarket
from agentlite.tools.multiagent.task import Task


async def main():
    """Run subagent example."""

    print("=" * 60)
    print("AgentLite Subagent Example")
    print("=" * 60)

    # Note: This example requires a valid API key
    # Replace with your actual API key to run
    api_key = "your-api-key"

    if api_key == "your-api-key":
        print("\nNOTE: Set your API key to run this example")
        print("Example code is shown below:\n")
        print("-" * 40)

    # Create provider
    provider = OpenAIProvider(api_key=api_key, model="gpt-4")

    # Example 1: Create subagents manually
    print("\n=== Example 1: Manual Subagent Setup ===")

    # Create parent agent with empty labor market
    parent = Agent(
        provider=provider,
        system_prompt="You are a coordinator agent that delegates tasks to specialists.",
        name="coordinator",
    )

    # Create subagents
    coder = Agent(
        provider=provider,
        system_prompt="You are a coding specialist. Write clean, well-documented code.",
        name="coder",
    )

    reviewer = Agent(
        provider=provider,
        system_prompt="You are a code reviewer. Provide constructive feedback.",
        name="reviewer",
    )

    # Register subagents with parent
    parent.add_subagent("coder", coder, "Writes code", dynamic=False)
    parent.add_subagent("reviewer", reviewer, "Reviews code", dynamic=False)

    # Add Task tool to parent
    parent.tools.add(Task(labor_market=parent.labor_market))

    print("Created parent agent with subagents:")
    print(f"  - coder: Writes code")
    print(f"  - reviewer: Reviews code")

    # Example 2: Using subagents
    print("\n=== Example 2: Delegating Tasks ===")

    # Parent agent delegates to coder
    # response = await parent.run(
    #     "I need a Python function to calculate fibonacci numbers. "
    #     "Use the coder subagent to write it."
    # )
    print("(Requires API key - uncomment to run)")

    # Example 3: Nested subagents (hierarchy)
    print("\n=== Example 3: Hierarchical Structure ===")

    # Create a team lead with team members as subagents
    team_lead = Agent(
        provider=provider,
        system_prompt="You are a team lead. Coordinate work among your team members.",
        name="team_lead",
    )

    # Create team members
    backend_dev = Agent(
        provider=provider,
        system_prompt="You are a backend developer. Focus on API design and database.",
        name="backend_dev",
    )

    frontend_dev = Agent(
        provider=provider,
        system_prompt="You are a frontend developer. Focus on UI/UX.",
        name="frontend_dev",
    )

    tester = Agent(
        provider=provider,
        system_prompt="You are a QA engineer. Write test cases and find bugs.",
        name="tester",
    )

    # Add subagents to team lead
    team_lead.add_subagent("backend", backend_dev, "Backend development")
    team_lead.add_subagent("frontend", frontend_dev, "Frontend development")
    team_lead.add_subagent("qa", tester, "Quality assurance")

    # Add Task tool
    team_lead.tools.add(Task(labor_market=team_lead.labor_market))

    print("Created team hierarchy:")
    print("  team_lead/")
    print("    ├── backend: Backend development")
    print("    ├── frontend: Frontend development")
    print("    └── qa: Quality assurance")

    # Example 4: Dynamic subagents
    print("\n=== Example 4: Dynamic Subagents ===")

    # Create subagent dynamically
    specialist = Agent(
        provider=provider,
        system_prompt="You are a specialist for a specific task.",
        name="specialist",
    )

    # Add as dynamic subagent
    team_lead.add_subagent("specialist", specialist, "Temporary specialist", dynamic=True)

    print("Added dynamic subagent 'specialist' to team_lead")

    # Example 5: Agent discovery
    print("\n=== Example 5: Agent Discovery ===")

    print(f"Team lead's subagents: {team_lead.labor_market.list_subagents()}")
    print(f"Descriptions: {team_lead.labor_market.subagent_descriptions}")

    # Check if subagent exists
    if "backend" in team_lead.labor_market:
        print("Backend subagent is available")

    # Get specific subagent
    backend = team_lead.get_subagent("backend")
    print(f"Backend agent name: {backend.name if backend else 'not found'}")

    # Example 6: Create subagent copy
    print("\n=== Example 6: Subagent Copy ===")

    # Create a copy of parent for use as subagent elsewhere
    parent_copy = parent.create_subagent_copy()
    print(f"Created copy of parent: {parent_copy.name}")
    print(f"Copy has empty labor market: {len(parent_copy.labor_market) == 0}")

    print("\n" + "=" * 60)
    print("Examples Complete")
    print("=" * 60)
    print("\nKey Concepts:")
    print("1. Parent agent holds subagents in LaborMarket")
    print("2. Task tool allows parent to delegate to subagents")
    print("3. Subagents have independent history and context")
    print("4. Fixed subagents are defined at setup")
    print("5. Dynamic subagents can be added at runtime")


if __name__ == "__main__":
    asyncio.run(main())
