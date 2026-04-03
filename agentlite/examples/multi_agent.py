"""Example: Multi-Agent Usage

This example demonstrates using multiple agents working independently.
"""

import asyncio
import os

from agentlite import Agent, OpenAIProvider


async def main():
    """Run the multi-agent example."""
    # Create provider
    provider = OpenAIProvider(
        api_key=os.getenv("OPENAI_API_KEY", "your-api-key"),
        model="gpt-4o-mini",
    )

    # Create specialized agents
    researcher = Agent(
        provider=provider,
        system_prompt="You are a research assistant. Provide factual, well-researched information.",
    )

    writer = Agent(
        provider=provider,
        system_prompt="You are a creative writer. Write engaging and clear content.",
    )

    critic = Agent(
        provider=provider,
        system_prompt="You are an editor. Review and improve content for clarity and accuracy.",
    )

    # Research phase
    print("=== Research Phase ===")
    topic = "artificial intelligence in healthcare"
    research = await researcher.run(f"Research {topic}. Provide key points.")
    print(f"Research:\n{research}\n")

    # Writing phase
    print("=== Writing Phase ===")
    content = await writer.run(f"Write a blog post about {topic} using this research:\n{research}")
    print(f"Draft:\n{content}\n")

    # Review phase
    print("=== Review Phase ===")
    review = await critic.run(f"Review this blog post and suggest improvements:\n{content}")
    print(f"Review:\n{review}\n")


if __name__ == "__main__":
    asyncio.run(main())
