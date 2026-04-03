"""Debug script to find CLI test hang cause."""

from __future__ import annotations

import os
import sys
import asyncio
import signal

sys.path.insert(0, "/home/tcmofashi/proj/l2d_backend/agentlite/src")

from agentlite import Agent, OpenAIProvider
from agentlite.tools.shell.shell import Shell, Params

SILICONFLOW_BASE_URL = "https://api.siliconflow.cn/v1"
SILICONFLOW_MODEL = "Qwen/Qwen3.5-397B-A17B"


async def test_shell_directly():
    """Test shell tool without agent."""
    print("\n=== Test 1: Shell tool directly ===")
    shell = Shell(timeout=10)

    # Use Params dataclass
    result = await shell(Params(command="echo 'Hello'", timeout=5))
    print(f"Result: {result}")
    print(f"Output: {result.output if hasattr(result, 'output') else result}")
    return True


async def test_agent_no_tools():
    """Test agent without tools."""
    print("\n=== Test 2: Agent without tools ===")
    api_key = os.environ.get("SILICONFLOW_API_KEY")
    if not api_key:
        print("SILICONFLOW_API_KEY not set")
        return False

    provider = OpenAIProvider(
        api_key=api_key,
        base_url=SILICONFLOW_BASE_URL,
        model=SILICONFLOW_MODEL,
        timeout=30.0,
    )

    agent = Agent(
        provider=provider,
        system_prompt="Reply briefly in one word.",
        max_iterations=3,
    )

    print("Sending message to LLM...")
    try:
        response = await asyncio.wait_for(
            agent.run("Say hello."),
            timeout=60.0,
        )
        print(f"Response: {response[:100]}...")
        return True
    except asyncio.TimeoutError:
        print("TIMEOUT in agent without tools!")
        return False


async def test_agent_with_shell():
    """Test agent with shell tool - the problematic case."""
    print("\n=== Test 3: Agent WITH shell tool ===")
    api_key = os.environ.get("SILICONFLOW_API_KEY")
    if not api_key:
        print("SILICONFLOW_API_KEY not set")
        return False

    provider = OpenAIProvider(
        api_key=api_key,
        base_url=SILICONFLOW_BASE_URL,
        model=SILICONFLOW_MODEL,
        timeout=60.0,
    )

    agent = Agent(
        provider=provider,
        system_prompt="You are a shell assistant. Execute commands when asked. Keep responses brief.",
        tools=[Shell(timeout=10)],
        max_iterations=5,  # Limit iterations
    )

    print("Sending message with tool request...")
    print("This is where it might hang...")

    try:
        response = await asyncio.wait_for(
            agent.run("Run 'echo test' and tell me the result."),
            timeout=120.0,
        )
        print(f"Response: {response}")
        return True
    except asyncio.TimeoutError:
        print("TIMEOUT! Agent hung for 120 seconds")

        # Check history to see what happened
        print(f"\nHistory length: {len(agent.history)}")
        for i, msg in enumerate(agent.history[-5:]):
            content_preview = str(msg.content)[:100] if msg.content else "None"
            print(f"  [{i}] {msg.role}: {content_preview}...")
        return False


async def main():
    """Run all tests."""
    print("=" * 60)
    print("CLI Debug Test - Finding the hang cause")
    print("=" * 60)

    results = []

    # Test 1: Shell directly
    r1 = await test_shell_directly()
    results.append(("Shell directly", r1))
    print(f"Result: {'PASS' if r1 else 'FAIL'}")

    # Test 2: Agent without tools
    r2 = await test_agent_no_tools()
    results.append(("Agent no tools", r2))
    print(f"Result: {'PASS' if r2 else 'FAIL'}")

    # Test 3: Agent with shell (the problem)
    r3 = await test_agent_with_shell()
    results.append(("Agent with shell", r3))
    print(f"Result: {'PASS' if r3 else 'FAIL'}")

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {name}: {status}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
