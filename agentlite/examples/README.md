# AgentLite Examples

This directory contains examples demonstrating various features of AgentLite.

## Setup

Before running the examples, set your OpenAI API key:

```bash
export OPENAI_API_KEY="sk-..."
```

Or create a `.env` file:

```
OPENAI_API_KEY=sk-...
```

## Examples

### 1. Single Agent (`single_agent.py`)

Basic usage of a single agent with conversation history.

```bash
python examples/single_agent.py
```

### 2. Multi-Agent (`multi_agent.py`)

Multiple specialized agents working together on a task.

```bash
python examples/multi_agent.py
```

### 3. Custom Tools (`custom_tools.py`)

Defining and using custom tools with agents.

```bash
python examples/custom_tools.py
```

### 4. MCP Tools (`mcp_tools.py`)

Using tools from MCP (Model Context Protocol) servers.

**Prerequisites:**
- Node.js installed
- MCP filesystem server: `npm install -g @modelcontextprotocol/server-filesystem`

```bash
python examples/mcp_tools.py
```

## Creating Your Own

Use these examples as templates for your own applications:

```python
import asyncio
from agentlite import Agent, OpenAIProvider

async def main():
    provider = OpenAIProvider(
        api_key="your-api-key",
        model="gpt-4",
    )
    
    agent = Agent(
        provider=provider,
        system_prompt="Your system prompt here.",
    )
    
    response = await agent.run("Your question here")
    print(response)

asyncio.run(main())
```
