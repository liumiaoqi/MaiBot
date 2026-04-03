"""Simple LLM client for direct LLM calls without agent overhead.

This module provides a simple interface for making direct LLM calls,
reusing the agentlite configuration system.

Example:
    >>> from agentlite import LLMClient, AgentConfig, ProviderConfig, ModelConfig
    >>>
    >>> # Using configuration
    >>> config = AgentConfig(
    ...     providers={"openai": ProviderConfig(api_key="sk-...")},
    ...     models={"gpt4": ModelConfig(provider="openai", model="gpt-4")},
    ...     default_model="gpt4",
    ... )
    >>> client = LLMClient(config)
    >>>
    >>> # Simple completion
    >>> response = await client.complete(
    ...     system_prompt="You are a helpful assistant.", user_prompt="What is Python?"
    ... )
    >>> print(response)

    >>> # Streaming
    >>> async for chunk in client.stream(
    ...     system_prompt="You are a helpful assistant.", user_prompt="Tell me a story"
    ... ):
    ...     print(chunk, end="")
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Optional

from agentlite.config import AgentConfig, ModelConfig, ProviderConfig
from agentlite.message import Message, TextPart
from agentlite.provider import ChatProvider, TokenUsage
from agentlite.providers.openai import OpenAIProvider
from agentlite.tool import Tool


class LLMResponse:
    """Response from an LLM call.

    Attributes:
        content: The complete response text
        usage: Token usage statistics
        model: The model name used
    """

    def __init__(self, content: str, usage: TokenUsage | None = None, model: str = ""):
        self.content = content
        self.usage = usage
        self.model = model

    def __str__(self) -> str:
        return self.content

    def __repr__(self) -> str:
        return f"LLMResponse(content={self.content[:50]}..., model={self.model})"


class LLMClient:
    """Simple client for direct LLM calls.

    This client provides a simple interface for calling LLMs without the
    overhead of an Agent. It reuses the agentlite configuration system.

    Example:
        >>> # Using AgentConfig
        >>> config = AgentConfig(...)
        >>> client = LLMClient(config)
        >>>
        >>> # Using provider directly
        >>> provider = OpenAIProvider(api_key="sk-...", model="gpt-4")
        >>> client = LLMClient(provider=provider)
        >>>
        >>> # Make a call
        >>> response = await client.complete(system_prompt="You are helpful.", user_prompt="Hello!")
    """

    def __init__(
        self,
        config: Optional[AgentConfig] = None,
        provider: Optional[ChatProvider] = None,
        model: Optional[str] = None,
    ):
        """Initialize the LLM client.

        Args:
            config: AgentConfig to use for provider/model configuration
            provider: Direct provider instance (alternative to config)
            model: Model name to use (when using config)

        Raises:
            ValueError: If neither config nor provider is provided
        """
        if provider is not None:
            self._provider = provider
            self._model_config = None
        elif config is not None:
            self._config = config
            self._model_name = model or config.default_model
            self._provider = self._create_provider()
            self._model_config = config.get_model_config(self._model_name)
        else:
            raise ValueError("Either config or provider must be provided")

    def _create_provider(self) -> ChatProvider:
        """Create a provider instance from config."""
        if not hasattr(self, "_config"):
            raise RuntimeError("No config available")

        provider_config = self._config.get_provider_config(self._model_name)
        model_config = self._config.get_model_config(self._model_name)

        # Create appropriate provider based on type
        if provider_config.type == "openai":
            return OpenAIProvider(
                api_key=provider_config.api_key.get_secret_value(),
                model=model_config.model,
                base_url=provider_config.base_url,
                timeout=provider_config.timeout,
            )
        else:
            raise ValueError(f"Unsupported provider type: {provider_config.type}")

    async def complete(
        self,
        user_prompt: str,
        system_prompt: str = "You are a helpful assistant.",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """Make a non-streaming LLM call.

        Args:
            user_prompt: The user message/prompt
            system_prompt: The system prompt (default: "You are a helpful assistant.")
            temperature: Sampling temperature (overrides config if provided)
            max_tokens: Maximum tokens to generate (overrides config if provided)

        Returns:
            LLMResponse containing the complete response text and metadata

        Example:
            >>> response = await client.complete(user_prompt="What is the capital of France?")
            >>> print(response.content)
            "The capital of France is Paris."
        """
        # Build messages
        messages = [Message(role="user", content=user_prompt)]

        # Create a temporary provider with overridden parameters if needed
        provider = self._provider
        if temperature is not None or max_tokens is not None:
            provider = self._create_provider_with_params(temperature, max_tokens)

        # Generate response
        stream = await provider.generate(
            system_prompt=system_prompt,
            tools=[],  # No tools for simple LLM calls
            history=messages,
        )

        # Collect response
        content_parts = []
        usage = None

        async for part in stream:
            if isinstance(part, TextPart):
                content_parts.append(part.text)
            # Try to get usage from stream
            try:
                if usage is None and hasattr(stream, "usage") and stream.usage:
                    usage = stream.usage
            except:
                pass

        content = "".join(content_parts)
        model_name = getattr(
            provider, "model_name", self._model_config.model if self._model_config else "unknown"
        )

        return LLMResponse(
            content=content,
            usage=usage,
            model=model_name,
        )

    async def stream(
        self,
        user_prompt: str,
        system_prompt: str = "You are a helpful assistant.",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[str]:
        """Make a streaming LLM call.

        Args:
            user_prompt: The user message/prompt
            system_prompt: The system prompt (default: "You are a helpful assistant.")
            temperature: Sampling temperature (overrides config if provided)
            max_tokens: Maximum tokens to generate (overrides config if provided)

        Yields:
            Response text chunks as they arrive

        Example:
            >>> async for chunk in client.stream(user_prompt="Write a poem about AI"):
            ...     print(chunk, end="")
        """
        # Build messages
        messages = [Message(role="user", content=user_prompt)]

        # Create a temporary provider with overridden parameters if needed
        provider = self._provider
        if temperature is not None or max_tokens is not None:
            provider = self._create_provider_with_params(temperature, max_tokens)

        # Generate response
        stream = await provider.generate(
            system_prompt=system_prompt,
            tools=[],  # No tools for simple LLM calls
            history=messages,
        )

        # Yield chunks
        async for part in stream:
            if isinstance(part, TextPart):
                yield part.text

    def _create_provider_with_params(
        self,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> ChatProvider:
        """Create a provider with overridden parameters."""
        if not hasattr(self, "_config"):
            # Can't override params without config
            return self._provider

        provider_config = self._config.get_provider_config(self._model_name)
        model_config = self._config.get_model_config(self._model_name)

        # Override parameters
        temp = temperature if temperature is not None else model_config.temperature
        max_tok = max_tokens if max_tokens is not None else model_config.max_tokens

        if provider_config.type == "openai":
            return OpenAIProvider(
                api_key=provider_config.api_key.get_secret_value(),
                model=model_config.model,
                base_url=provider_config.base_url,
                timeout=provider_config.timeout,
                temperature=temp,
                max_tokens=max_tok,
            )
        else:
            raise ValueError(f"Unsupported provider type: {provider_config.type}")


# Convenience functions for simple use cases


async def llm_complete(
    user_prompt: str,
    system_prompt: str = "You are a helpful assistant.",
    api_key: Optional[str] = None,
    model: str = "gpt-4",
    base_url: str = "https://api.openai.com/v1",
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> str:
    """Simple function for one-off LLM completions.

    This is a convenience function for simple use cases where you don't
    need to reuse a client instance.

    Args:
        user_prompt: The user message/prompt
        system_prompt: The system prompt
        api_key: API key (if not provided, must be set in env)
        model: Model name (default: gpt-4)
        base_url: API base URL
        temperature: Sampling temperature
        max_tokens: Maximum tokens to generate

    Returns:
        The response text

    Example:
        >>> response = await llm_complete(
        ...     user_prompt="What is 2+2?",
        ...     api_key="sk-...",
        ...     model="gpt-4",
        ... )
        >>> print(response)
        "2+2 equals 4."
    """
    provider = OpenAIProvider(
        api_key=api_key,
        model=model,
        base_url=base_url,
    )
    client = LLMClient(provider=provider)
    response = await client.complete(
        user_prompt=user_prompt,
        system_prompt=system_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.content


async def llm_stream(
    user_prompt: str,
    system_prompt: str = "You are a helpful assistant.",
    api_key: Optional[str] = None,
    model: str = "gpt-4",
    base_url: str = "https://api.openai.com/v1",
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> AsyncIterator[str]:
    """Simple function for one-off streaming LLM completions.

    This is a convenience function for simple use cases where you don't
    need to reuse a client instance.

    Args:
        user_prompt: The user message/prompt
        system_prompt: The system prompt
        api_key: API key (if not provided, must be set in env)
        model: Model name (default: gpt-4)
        base_url: API base URL
        temperature: Sampling temperature
        max_tokens: Maximum tokens to generate

    Yields:
        Response text chunks

    Example:
        >>> async for chunk in llm_stream(
        ...     user_prompt="Write a haiku",
        ...     api_key="sk-...",
        ... ):
        ...     print(chunk, end="")
    """
    provider = OpenAIProvider(
        api_key=api_key,
        model=model,
        base_url=base_url,
    )
    client = LLMClient(provider=provider)
    async for chunk in client.stream(
        user_prompt=user_prompt,
        system_prompt=system_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
    ):
        yield chunk
