"""Example: MCP Tools

This example demonstrates how to use MCP (Model Context Protocol) tools
with AgentLite agents.

Note: This example requires an MCP server to be available.
"""

import asyncio
import os

from agentlite import Agent, MCPClient, OpenAIProvider


async def main():
    """Run the MCP tools example."""
    # Create provider
    provider = OpenAIProvider(
        api_key=os.getenv("OPENAI_API_KEY", "your-api-key"),
        model="gpt-4o-mini",
    )

    # Connect to MCP server
    # This example uses the filesystem MCP server
    # You can install it with: npm install -g @modelcontextprotocol/server-filesystem

    print("Connecting to MCP server...")

    async with MCPClient() as mcp:
        # Connect via stdio
        await mcp.connect_stdio(
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
        )

        # Load tools from MCP server
        print("Loading MCP tools...")
        mcp_tools = await mcp.load_tools()
        print(f"Loaded {len(mcp_tools)} tools from MCP server")

        # Create agent with MCP tools
        agent = Agent(
            provider=provider,
            system_prompt="You are a helpful assistant with access to filesystem tools.",
            tools=mcp_tools,
        )

        # Test MCP tools
        print("\n=== Testing MCP Tools ===\n")

        print("User: List files in /tmp")
        response = await agent.run("List files in /tmp")
        print(f"Agent: {response}\n")

        print("User: Create a file called test.txt with 'Hello from AgentLite!'")
        response = await agent.run(
            "Create a file called test.txt with content 'Hello from AgentLite!'"
        )
        print(f"Agent: {response}\n")

        print("User: Read the test.txt file")
        response = await agent.run("Read the test.txt file")
        print(f"Agent: {response}\n")


if __name__ == "__main__":
    # Note: This example requires Node.js and the MCP filesystem server
    # npm install -g @modelcontextprotocol/server-filesystem
    print("Note: This example requires Node.js and @modelcontextprotocol/server-filesystem")
    print("Install with: npm install -g @modelcontextprotocol/server-filesystem\n")

    try:
        asyncio.run(main())
    except Exception as e:
        print(f"Error: {e}")
        print("\nMake sure you have:")
        print("1. Node.js installed")
        print("2. @modelcontextprotocol/server-filesystem installed globally")
        print("3. OPENAI_API_KEY environment variable set")
