"""Example: Single Agent Usage

This example demonstrates basic usage of the AgentLite Agent class.
"""

import asyncio
import os

from agentlite import Agent, OpenAIProvider


async def main():
    """Run the single agent example."""
    # Create provider
    provider = OpenAIProvider(
        api_key=os.getenv("OPENAI_API_KEY", "your-api-key"),
        model="gpt-4o-mini",
    )

    # Create agent
    agent = Agent(
        provider=provider,
        system_prompt="You are a helpful assistant. Be concise.",
    )

    # Run conversation
    print("User: What is Python?")
    response = await agent.run("What is Python?")
    print(f"Agent: {response}\n")

    print("User: What are its main features?")
    response = await agent.run("What are its main features?")
    print(f"Agent: {response}\n")

    # Show conversation history
    print("--- Conversation History ---")
    for msg in agent.history:
        print(f"{msg.role}: {msg.extract_text()[:100]}...")


if __name__ == "__main__":
    asyncio.run(main())
