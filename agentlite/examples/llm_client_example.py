"""Example demonstrating LLMClient usage.

This example shows how to use LLMClient for simple LLM calls
without the overhead of an Agent.
"""

import asyncio

from agentlite import LLMClient
from agentlite.config import AgentConfig, ProviderConfig, ModelConfig


async def main():
    """Run LLM client examples."""

    # Example 1: Using simple function interface
    print("=== Example 1: Simple Function ===")
    print("Using llm_complete() function:")

    # Note: This requires a valid API key
    # response = await llm_complete(
    #     user_prompt="What is Python?",
    #     api_key="your-api-key",
    #     model="gpt-4",
    # )
    # print(response)

    print("(Requires API key - uncomment to run)")

    # Example 2: Using configuration-based client
    print("\n=== Example 2: Configuration-Based Client ===")

    config = AgentConfig(
        name="simple_llm",
        system_prompt="You are a helpful coding assistant.",
        providers={
            "openai": ProviderConfig(
                type="openai",
                api_key="your-api-key",  # Replace with actual key
            )
        },
        models={
            "gpt4": ModelConfig(
                provider="openai",
                model="gpt-4",
                temperature=0.7,
            ),
            "gpt35": ModelConfig(
                provider="openai",
                model="gpt-3.5-turbo",
                temperature=0.5,
            ),
        },
        default_model="gpt4",
    )

    # Create client
    LLMClient(config)

    # Make a call
    # response = await client.complete(
    #     user_prompt="Explain async/await in Python",
    # )
    # print(f"Response: {response.content}")
    # print(f"Model: {response.model}")
    # if response.usage:
    #     print(f"Tokens: {response.usage.total}")

    print("(Requires API key - uncomment to run)")

    # Example 3: Streaming
    print("\n=== Example 3: Streaming ===")
    print("Using llm_stream() function:")

    # async for chunk in llm_stream(
    #     user_prompt="Write a haiku about programming",
    #     api_key="your-api-key",
    # ):
    #     print(chunk, end="")

    print("\n(Requires API key - uncomment to run)")

    # Example 4: Direct provider usage
    print("\n=== Example 4: Direct Provider ===")

    from agentlite import OpenAIProvider

    provider = OpenAIProvider(
        api_key="your-api-key",
        model="gpt-4",
        temperature=0.8,
    )

    LLMClient(provider=provider)

    # response = await client.complete(
    #     user_prompt="What are the benefits of type hints?",
    #     system_prompt="You are a Python expert.",
    # )
    # print(response.content)

    print("(Requires API key - uncomment to run)")

    # Example 5: Model switching
    print("\n=== Example 5: Model Switching ===")

    # Use default model (gpt4)
    # response1 = await client.complete(user_prompt="Hello!")

    # Switch to different model
    # client_gpt35 = LLMClient(config, model="gpt35")
    # response2 = await client_gpt35.complete(user_prompt="Hello!")

    print("(Requires API key - uncomment to run)")

    print("\n=== Examples Complete ===")
    print("To run these examples:")
    print("1. Set your OpenAI API key")
    print("2. Uncomment the example code")
    print("3. Run: python examples/llm_client_example.py")


if __name__ == "__main__":
    asyncio.run(main())
