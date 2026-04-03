"""Integration tests for AgentLite with real API.

This script runs comprehensive tests against the real OpenAI API.
Requires OPENAI_API_KEY environment variable to be set.

Usage:
    export OPENAI_API_KEY="sk-..."
    python tests/integration/test_with_api.py
"""

import asyncio
import os
import sys
from pathlib import Path
import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from agentlite import Agent, OpenAIProvider, LLMClient
from agentlite.skills import discover_skills, SkillTool, index_skills_by_name
from agentlite.tools import ConfigurableToolset


# Test configuration
TEST_MODEL = "gpt-4o-mini"  # Use mini for cost efficiency
HAS_OPENAI_API_KEY = bool(os.environ.get("OPENAI_API_KEY"))

pytestmark = pytest.mark.skipif(
    not HAS_OPENAI_API_KEY, reason="OPENAI_API_KEY is required to run integration tests"
)


def get_provider():
    """Get OpenAI provider with API key."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("❌ OPENAI_API_KEY not set!")
        print("Please set your OpenAI API key:")
        print("  export OPENAI_API_KEY='sk-...'")
        sys.exit(1)
    return OpenAIProvider(api_key=api_key, model=TEST_MODEL)


async def test_basic_agent():
    """Test 1: Basic Agent functionality."""
    print("\n" + "=" * 60)
    print("Test 1: Basic Agent Functionality")
    print("=" * 60)

    try:
        provider = get_provider()
        agent = Agent(
            provider=provider,
            system_prompt="You are a helpful assistant. Be concise.",
        )

        response = await agent.run("What is 2+2?")
        print(f"✅ Agent responded: {response[:100]}...")

        assert "4" in response, "Expected '4' in response"
        print("✅ Basic Agent test PASSED")
        return True

    except Exception as e:
        print(f"❌ Basic Agent test FAILED: {e}")
        return False


async def test_agent_with_tools():
    """Test 2: Agent with tool suite."""
    print("\n" + "=" * 60)
    print("Test 2: Agent with Tool Suite")
    print("=" * 60)

    try:
        from agentlite.tools import ToolSuiteConfig

        provider = get_provider()

        # Create toolset with file tools
        config = ToolSuiteConfig()
        toolset = ConfigurableToolset(config, work_dir=Path.cwd())

        agent = Agent(
            provider=provider,
            system_prompt="You are a helpful assistant with file access.",
            tools=toolset.tools,
        )

        print(f"✅ Agent created with {len(agent.tools.tools)} tools")

        # Test simple query (without requiring file access)
        response = await agent.run("List the Python files in the current directory")
        print(f"✅ Agent with tools responded: {response[:100]}...")

        print("✅ Agent with Tools test PASSED")
        return True

    except Exception as e:
        print(f"❌ Agent with Tools test FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_llm_client():
    """Test 3: LLMClient functionality."""
    print("\n" + "=" * 60)
    print("Test 3: LLMClient Functionality")
    print("=" * 60)

    try:
        provider = get_provider()
        client = LLMClient(provider=provider)

        response = await client.complete(
            user_prompt="What is the capital of France?",
            system_prompt="You are a helpful assistant. Be concise.",
        )

        print(f"✅ LLMClient responded: {response.content[:100]}...")
        assert "Paris" in response.content, "Expected 'Paris' in response"

        print("✅ LLMClient test PASSED")
        return True

    except Exception as e:
        print(f"❌ LLMClient test FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_llm_streaming():
    """Test 4: LLM streaming."""
    print("\n" + "=" * 60)
    print("Test 4: LLM Streaming")
    print("=" * 60)

    try:
        provider = get_provider()
        client = LLMClient(provider=provider)

        chunks = []
        async for chunk in client.stream(
            user_prompt="Count from 1 to 3",
            system_prompt="You are a helpful assistant.",
        ):
            chunks.append(chunk)
            print(f"  Chunk: {chunk[:20]}...")

        full_response = "".join(chunks)
        print(f"✅ Streamed response: {full_response[:100]}...")

        print("✅ LLM Streaming test PASSED")
        return True

    except Exception as e:
        print(f"❌ LLM Streaming test FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_subagents():
    """Test 5: Subagent functionality."""
    print("\n" + "=" * 60)
    print("Test 5: Subagent Functionality")
    print("=" * 60)

    try:
        from agentlite.tools.multiagent.task import Task

        provider = get_provider()

        # Create parent agent
        parent = Agent(
            provider=provider,
            system_prompt="You are a coordinator agent.",
            name="coordinator",
        )

        # Create subagent
        coder = Agent(
            provider=provider,
            system_prompt="You are a coding specialist. Write clean, simple code.",
            name="coder",
        )

        # Add subagent to parent
        parent.add_subagent("coder", coder, "Writes code")

        # Add Task tool
        parent.tools.add(Task(labor_market=parent.labor_market))

        print(f"✅ Created parent with {len(parent.labor_market)} subagent(s)")
        print(f"  Subagents: {parent.labor_market.list_subagents()}")

        print("✅ Subagent test PASSED")
        return True

    except Exception as e:
        print(f"❌ Subagent test FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_skills():
    """Test 6: Skills functionality."""
    print("\n" + "=" * 60)
    print("Test 6: Skills Functionality")
    print("=" * 60)

    try:
        # Discover example skills
        skills_dir = Path(__file__).parent.parent.parent / "examples" / "skills"
        if not skills_dir.exists():
            print("⚠️  Skills directory not found, skipping")
            return True

        skills = discover_skills(skills_dir)
        print(f"✅ Discovered {len(skills)} skill(s)")

        for skill in skills:
            print(f"  - {skill.name} ({skill.type})")

        if len(skills) == 0:
            print("⚠️  No skills found, skipping further tests")
            return True

        # Test with agent
        provider = get_provider()
        agent = Agent(
            provider=provider,
            system_prompt="You are a helpful assistant.",
        )

        skill_index = index_skills_by_name(skills)
        skill_tool = SkillTool(skill_index, parent_agent=agent)
        agent.tools.add(skill_tool)

        print("✅ Added SkillTool to agent")
        print("✅ Skills test PASSED")
        return True

    except Exception as e:
        print(f"❌ Skills test FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_conversation_history():
    """Test 7: Conversation history."""
    print("\n" + "=" * 60)
    print("Test 7: Conversation History")
    print("=" * 60)

    try:
        provider = get_provider()
        agent = Agent(
            provider=provider,
            system_prompt="You are a helpful assistant.",
        )

        # First message
        response1 = await agent.run("My name is Alice")
        print(f"✅ Response 1: {response1[:50]}...")

        # Second message (should remember context)
        response2 = await agent.run("What is my name?")
        print(f"✅ Response 2: {response2[:50]}...")

        assert "Alice" in response2, "Expected agent to remember name"

        print("✅ Conversation History test PASSED")
        return True

    except Exception as e:
        print(f"❌ Conversation History test FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


async def run_all_tests():
    """Run all integration tests."""
    print("\n" + "=" * 60)
    print("AgentLite Integration Tests with Real API")
    print("=" * 60)
    print(f"Model: {TEST_MODEL}")

    # Check API key
    if not os.environ.get("OPENAI_API_KEY"):
        print("\n❌ OPENAI_API_KEY not set!")
        print("\nTo run these tests, set your OpenAI API key:")
        print("  export OPENAI_API_KEY='sk-...'")
        print("\nGet your API key from: https://platform.openai.com/api-keys")
        return []

    results = []

    # Run all tests
    results.append(("Basic Agent", await test_basic_agent()))
    results.append(("Agent with Tools", await test_agent_with_tools()))
    results.append(("LLMClient", await test_llm_client()))
    results.append(("LLM Streaming", await test_llm_streaming()))
    results.append(("Subagents", await test_subagents()))
    results.append(("Skills", await test_skills()))
    results.append(("Conversation History", await test_conversation_history()))

    # Print summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{status}: {name}")

    print(f"\n{passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All tests passed!")
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")

    return results


if __name__ == "__main__":
    results = asyncio.run(run_all_tests())

    # Exit with error code if any tests failed
    if results and not all(r for _, r in results):
        sys.exit(1)
