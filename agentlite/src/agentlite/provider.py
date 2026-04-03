"""Chat provider protocol and implementations for AgentLite.

This module defines the ChatProvider protocol that abstracts LLM providers
and provides the base types for streaming responses.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Protocol, runtime_checkable

from pydantic import BaseModel

from agentlite.message import ContentPart, Message, ToolCall, ToolCallPart
from agentlite.tool import Tool


class TokenUsage(BaseModel):
    """Token usage statistics for a generation.

    Attributes:
        input_tokens: Number of input tokens used.
        output_tokens: Number of output tokens generated.
        cached_tokens: Number of cached input tokens (if applicable).

    Example:
        >>> usage = TokenUsage(input_tokens=100, output_tokens=50)
        >>> print(usage.total)
        150
    """

    input_tokens: int
    """Number of input tokens used."""

    output_tokens: int
    """Number of output tokens generated."""

    cached_tokens: int = 0
    """Number of cached input tokens (if applicable)."""

    @property
    def total(self) -> int:
        """Total tokens used (input + output)."""
        return self.input_tokens + self.output_tokens


from typing import Union

StreamedPart = Union[ContentPart, ToolCall, ToolCallPart]


@runtime_checkable
class StreamedMessage(Protocol):
    """Protocol for streamed message responses.

    This protocol defines the interface for streaming responses from LLM
    providers. Implementations should yield content parts as they arrive.

    Example:
        >>> stream = await provider.generate(system_prompt, tools, history)
        >>> async for part in stream:
        ...     print(part)
    """

    def __aiter__(self) -> AsyncIterator[StreamedPart]:
        """Return an async iterator over the streamed parts."""
        ...

    @property
    def id(self) -> str | None:
        """The unique identifier of the message, if available."""
        ...

    @property
    def usage(self) -> TokenUsage | None:
        """Token usage statistics, if available."""
        ...


class ChatProviderError(Exception):
    """Base exception for chat provider errors."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class APIConnectionError(ChatProviderError):
    """Error connecting to the API."""

    pass


class APITimeoutError(ChatProviderError):
    """API request timed out."""

    pass


class APIStatusError(ChatProviderError):
    """API returned an error status code.

    Attributes:
        status_code: The HTTP status code returned.
    """

    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


class APIEmptyResponseError(ChatProviderError):
    """API returned an empty response."""

    pass


@runtime_checkable
class ChatProvider(Protocol):
    """Protocol for LLM chat providers.

    This protocol defines the interface that all LLM providers must implement.
    It supports both streaming and non-streaming generation.

    Example:
        >>> provider = OpenAIProvider(api_key="sk-...", model="gpt-4")
        >>> stream = await provider.generate(
        ...     system_prompt="You are helpful.",
        ...     tools=[],
        ...     history=[Message(role="user", content="Hello!")],
        ... )
        >>> async for part in stream:
        ...     print(part)
    """

    @property
    def model_name(self) -> str:
        """The name of the model being used."""
        ...

    async def generate(
        self,
        system_prompt: str,
        tools: Sequence[Tool],
        history: Sequence[Message],
    ) -> StreamedMessage:
        """Generate a response from the LLM.

        Args:
            system_prompt: The system prompt to use.
            tools: Available tools for the model to call.
            history: The conversation history.

        Returns:
            A streamed message that yields content parts.

        Raises:
            APIConnectionError: If the connection fails.
            APITimeoutError: If the request times out.
            APIStatusError: If the API returns an error status.
            APIEmptyResponseError: If the response is empty.
        """
        ...
