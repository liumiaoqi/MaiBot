# LLM Client

Simple LLM client for direct LLM calls without agent overhead.

## Overview

The `LLMClient` provides a simple interface for making direct LLM calls, reusing the agentlite configuration system. This is useful when you don't need the full agent capabilities (tools, conversation history, etc.) and just want to call an LLM.

## Features

- **Simple Interface**: Just system prompt + user prompt → response
- **Configuration Reuse**: Uses existing `AgentConfig` for provider/model setup
- **Streaming Support**: Both non-streaming and streaming interfaces
- **Flexible Usage**: Use with config, direct provider, or simple functions

## Quick Start

### Method 1: Simple Function (Quickest)

```python
import asyncio
from agentlite import llm_complete

async def main():
    response = await llm_complete(
        user_prompt="What is Python?",
        api_key="your-api-key",
        model="gpt-4",
    )
    print(response)

asyncio.run(main())
```

### Method 2: Using Configuration

```python
import asyncio
from agentlite import LLMClient, AgentConfig, ProviderConfig, ModelConfig

async def main():
    # Create configuration
    config = AgentConfig(
        providers={
            "openai": ProviderConfig(api_key="your-api-key")
        },
        models={
            "gpt4": ModelConfig(provider="openai", model="gpt-4")
        },
        default_model="gpt4",
    )
    
    # Create client
    client = LLMClient(config)
    
    # Make a call
    response = await client.complete(
        system_prompt="You are a helpful assistant.",
        user_prompt="What is Python?"
    )
    
    print(response.content)
    print(f"Model: {response.model}")
    if response.usage:
        print(f"Tokens: {response.usage.total}")

asyncio.run(main())
```

### Method 3: Direct Provider

```python
import asyncio
from agentlite import LLMClient, OpenAIProvider

async def main():
    # Create provider directly
    provider = OpenAIProvider(
        api_key="your-api-key",
        model="gpt-4",
        temperature=0.8,
    )
    
    # Create client
    client = LLMClient(provider=provider)
    
    # Make a call
    response = await client.complete(
        user_prompt="Explain async/await",
        system_prompt="You are a Python expert.",
    )
    
    print(response.content)

asyncio.run(main())
```

## Streaming

### Using Client

```python
async for chunk in client.stream(
    user_prompt="Write a poem about AI",
    system_prompt="You are a creative writer.",
):
    print(chunk, end="")
```

### Using Function

```python
async for chunk in llm_stream(
    user_prompt="Write a haiku",
    api_key="your-api-key",
):
    print(chunk, end="")
```

## API Reference

### LLMClient

```python
class LLMClient:
    def __init__(
        self,
        config: Optional[AgentConfig] = None,
        provider: Optional[ChatProvider] = None,
        model: Optional[str] = None,
    )
    
    async def complete(
        self,
        user_prompt: str,
        system_prompt: str = "You are a helpful assistant.",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse
    
    async def stream(
        self,
        user_prompt: str,
        system_prompt: str = "You are a helpful assistant.",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[str]
```

### LLMResponse

```python
class LLMResponse:
    content: str      # The response text
    usage: TokenUsage | None  # Token usage stats
    model: str        # Model name used
```

### Convenience Functions

```python
async def llm_complete(
    user_prompt: str,
    system_prompt: str = "You are a helpful assistant.",
    api_key: Optional[str] = None,
    model: str = "gpt-4",
    base_url: str = "https://api.openai.com/v1",
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> str

async def llm_stream(
    user_prompt: str,
    system_prompt: str = "You are a helpful assistant.",
    api_key: Optional[str] = None,
    model: str = "gpt-4",
    base_url: str = "https://api.openai.com/v1",
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> AsyncIterator[str]
```

## Configuration Options

### Temperature and Max Tokens

You can override temperature and max_tokens per call:

```python
response = await client.complete(
    user_prompt="Creative writing task",
    temperature=0.9,  # More creative
    max_tokens=500,   # Limit response length
)
```

### Model Switching

When using `AgentConfig`, you can switch models:

```python
config = AgentConfig(
    providers={"openai": ProviderConfig(api_key="...")},
    models={
        "gpt4": ModelConfig(provider="openai", model="gpt-4"),
        "gpt35": ModelConfig(provider="openai", model="gpt-3.5-turbo"),
    },
    default_model="gpt4",
)

# Use default model (gpt4)
client = LLMClient(config)

# Use specific model
client_gpt35 = LLMClient(config, model="gpt35")
```

## Comparison with Agent

| Feature | LLMClient | Agent |
|---------|-----------|-------|
| Tools | ❌ No | ✅ Yes |
| Conversation History | ❌ No | ✅ Yes |
| System Prompt | ✅ Yes | ✅ Yes |
| Configuration | ✅ Reuses AgentConfig | ✅ AgentConfig |
| Streaming | ✅ Yes | ✅ Yes |
| Use Case | Simple LLM calls | Complex agent workflows |

## Examples

### Translation

```python
async def translate(text: str, target_language: str) -> str:
    response = await llm_complete(
        user_prompt=f"Translate to {target_language}: {text}",
        system_prompt="You are a translator. Return only the translation.",
        api_key="your-api-key",
    )
    return response
```

### Code Review

```python
async def review_code(code: str) -> str:
    client = LLMClient(config)
    response = await client.complete(
        user_prompt=f"Review this code:\n\n```python\n{code}\n```",
        system_prompt="You are a code reviewer. Provide constructive feedback.",
    )
    return response.content
```

### Streaming Chat

```python
async def chat_stream(user_message: str):
    async for chunk in client.stream(
        user_prompt=user_message,
        system_prompt="You are a helpful chat assistant.",
    ):
        yield chunk
```

## Error Handling

```python
from agentlite.provider import APIConnectionError, APITimeoutError, APIStatusError

try:
    response = await client.complete(user_prompt="Hello")
except APIConnectionError:
    print("Failed to connect to API")
except APITimeoutError:
    print("Request timed out")
except APIStatusError as e:
    print(f"API error {e.status_code}: {e.message}")
```
