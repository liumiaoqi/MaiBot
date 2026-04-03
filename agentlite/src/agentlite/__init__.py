"""AgentLite - A lightweight, async-first Agent component library.

AgentLite provides clean abstractions for building LLM-powered agents with
OpenAI-compatible APIs, supporting tools (including MCP), streaming, and
multi-agent usage.

Example:
    >>> import asyncio
    >>> from agentlite import Agent, OpenAIProvider
    >>>
    >>> async def main():
    ...     provider = OpenAIProvider(api_key="sk-...", model="gpt-4")
    ...     agent = Agent(provider=provider, system_prompt="You are helpful.")
    ...     response = await agent.run("Hello!")
    ...     print(response)
    >>>
    >>> asyncio.run(main())
"""

__version__ = "0.1.0"

# Core types
from agentlite.message import (
    ContentPart,
    Message,
    Role,
    TextPart,
    ImageURLPart,
    AudioURLPart,
    ToolCall,
    ToolCallPart,
)
from agentlite.tool import (
    Tool,
    ToolResult,
    ToolOk,
    ToolError,
    CallableTool,
    CallableTool2,
    SimpleToolset,
    tool,
)
from agentlite.provider import (
    ChatProvider,
    StreamedMessage,
    TokenUsage,
    ChatProviderError,
    APIConnectionError,
    APITimeoutError,
    APIStatusError,
)

# Configuration
from agentlite.config import (
    ProviderConfig,
    ModelConfig,
    AgentConfig,
)

# Agent
from agentlite.agent import Agent

# MCP
from agentlite.mcp import MCPClient

# OpenAI Provider
from agentlite.providers.openai import OpenAIProvider

# LLM Client
from agentlite.llm_client import LLMClient, LLMResponse, llm_complete, llm_stream

__all__ = [
    # Version
    "__version__",
    # Message types
    "ContentPart",
    "Message",
    "Role",
    "TextPart",
    "ImageURLPart",
    "AudioURLPart",
    "ToolCall",
    "ToolCallPart",
    # Tool types
    "Tool",
    "ToolResult",
    "ToolOk",
    "ToolError",
    "CallableTool",
    "CallableTool2",
    "SimpleToolset",
    "tool",
    # Provider types
    "ChatProvider",
    "StreamedMessage",
    "TokenUsage",
    "ChatProviderError",
    "APIConnectionError",
    "APITimeoutError",
    "APIStatusError",
    # Configuration
    "ProviderConfig",
    "ModelConfig",
    "AgentConfig",
    # Agent
    "Agent",
    # MCP
    "MCPClient",
    # Providers
    "OpenAIProvider",
    # LLM Client
    "LLMClient",
    "LLMResponse",
    "llm_complete",
    "llm_stream",
]
