"""OpenAI provider implementation for AgentLite.

This module provides an OpenAI-compatible chat provider that works with
the OpenAI API and any OpenAI-compatible API (e.g., Moonshot, Together, etc.).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Sequence
from typing import TYPE_CHECKING, Any

import httpx
from openai import AsyncOpenAI, OpenAIError
from openai.types.chat import (
    ChatCompletion,
    ChatCompletionChunk,
    ChatCompletionMessageParam,
    ChatCompletionToolParam,
)

from agentlite.message import (
    Message,
    TextPart,
    ToolCall,
    ToolCallPart,
)
from agentlite.provider import (
    APIConnectionError,
    APIEmptyResponseError,
    APIStatusError,
    APITimeoutError,
    ChatProviderError,
    StreamedMessage,
    TokenUsage,
)
from agentlite.tool import Tool

if TYPE_CHECKING:
    pass


def _convert_tool_to_openai(tool: Tool) -> ChatCompletionToolParam:
    """Convert a Tool to OpenAI tool format.

    Args:
        tool: The tool to convert.

    Returns:
        The OpenAI tool format.
    """
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        },
    }


def _convert_message_to_openai(message: Message) -> ChatCompletionMessageParam:
    """Convert a Message to OpenAI message format.

    Args:
        message: The message to convert.

    Returns:
        The OpenAI message format.
    """
    # Start with basic message
    result: dict[str, Any] = {
        "role": message.role,
    }

    # Handle content
    if message.role == "tool":
        # Tool response message
        result["content"] = message.extract_text()
        result["tool_call_id"] = message.tool_call_id
    elif message.has_tool_calls():
        # Assistant message with tool calls
        result["content"] = message.extract_text() or None
        result["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in (message.tool_calls or [])
        ]
    else:
        # Regular message
        content_parts = []
        for part in message.content:
            if isinstance(part, TextPart):
                content_parts.append(part.text)
        result["content"] = "\n".join(content_parts) if content_parts else None

    return result  # type: ignore[return-value]


class OpenAIStreamedMessage:
    """Streamed message implementation for OpenAI.

    This class wraps the OpenAI streaming response and converts chunks
    into AgentLite content parts.
    """

    def __init__(self, response: AsyncIterator[ChatCompletionChunk]):
        """Initialize the streamed message.

        Args:
            response: The OpenAI streaming response.
        """
        self._response = response
        self._id: str | None = None
        self._usage = TokenUsage(input_tokens=0, output_tokens=0)

    def __aiter__(self) -> AsyncIterator[Any]:
        """Return an async iterator over the streamed parts."""
        return self._iter_chunks()

    async def _iter_chunks(self) -> AsyncIterator[Any]:
        """Iterate over response chunks and yield content parts."""
        try:
            async for chunk in self._response:
                # Track message ID
                if chunk.id:
                    self._id = chunk.id

                # Track usage if available
                if chunk.usage:
                    self._usage = TokenUsage(
                        input_tokens=chunk.usage.prompt_tokens,
                        output_tokens=chunk.usage.completion_tokens,
                    )

                # Skip empty choices
                if not chunk.choices:
                    continue

                delta = chunk.choices[0].delta

                # Yield text content
                if delta.content:
                    yield TextPart(text=delta.content)

                # Yield tool calls
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        if tc.function:
                            if tc.function.name:
                                # New tool call
                                yield ToolCall(
                                    id=tc.id or str(uuid.uuid4()),
                                    function=ToolCall.FunctionBody(
                                        name=tc.function.name,
                                        arguments=tc.function.arguments or "",
                                    ),
                                )
                            elif tc.function.arguments:
                                # Continuation of tool call arguments
                                yield ToolCallPart(arguments_part=tc.function.arguments)
        except (OpenAIError, httpx.HTTPError) as e:
            raise _convert_error(e) from e

    @property
    def id(self) -> str | None:
        """The unique identifier of the message."""
        return self._id

    @property
    def usage(self) -> TokenUsage | None:
        """Token usage statistics."""
        return self._usage


class OpenAIProvider:
    """OpenAI-compatible chat provider.

    This provider works with the OpenAI API and any OpenAI-compatible API
    such as Moonshot, Together, Fireworks, etc.

    Attributes:
        model: The model name to use.
        client: The underlying AsyncOpenAI client.

    Example:
        >>> provider = OpenAIProvider(
        ...     api_key="sk-...",
        ...     model="gpt-4",
        ... )
        >>> stream = await provider.generate(
        ...     system_prompt="You are helpful.",
        ...     tools=[],
        ...     history=[Message(role="user", content="Hello!")],
        ... )
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str | None = None,
        timeout: float = 60.0,
        **client_kwargs: Any,
    ):
        """Initialize the OpenAI provider.

        Args:
            api_key: The API key for authentication.
            model: The model name to use (e.g., "gpt-4", "gpt-3.5-turbo").
            base_url: Optional custom base URL for OpenAI-compatible APIs.
            timeout: Request timeout in seconds.
            **client_kwargs: Additional arguments passed to AsyncOpenAI.
        """
        self.model = model
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            **client_kwargs,
        )

    @property
    def model_name(self) -> str:
        """The name of the model being used."""
        return self.model

    async def generate(
        self,
        system_prompt: str,
        tools: Sequence[Tool],
        history: Sequence[Message],
    ) -> StreamedMessage:
        """Generate a response from the OpenAI API.

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
        # Build messages
        messages: list[ChatCompletionMessageParam] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        for msg in history:
            messages.append(_convert_message_to_openai(msg))

        # Build tools
        openai_tools = [_convert_tool_to_openai(t) for t in tools] if tools else None

        try:
            # Make streaming request
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=openai_tools,
                stream=True,
                stream_options={"include_usage": True},
            )

            return OpenAIStreamedMessage(response)  # type: ignore[arg-type]
        except (OpenAIError, httpx.HTTPError) as e:
            raise _convert_error(e) from e


def _convert_error(error: OpenAIError | httpx.HTTPError) -> ChatProviderError:
    """Convert an OpenAI or HTTP error to a ChatProviderError.

    Args:
        error: The error to convert.

    Returns:
        The appropriate ChatProviderError subclass.
    """
    if isinstance(error, OpenAIError):
        if isinstance(error, OpenAIError.APIConnectionError):
            return APIConnectionError(str(error))
        elif isinstance(error, OpenAIError.APITimeoutError):
            return APITimeoutError(str(error))
        elif isinstance(error, OpenAIError.APIStatusError):
            return APIStatusError(error.status_code, str(error))

    if isinstance(error, httpx.TimeoutException):
        return APITimeoutError(str(error))
    elif isinstance(error, httpx.NetworkError):
        return APIConnectionError(str(error))
    elif isinstance(error, httpx.HTTPStatusError):
        return APIStatusError(error.response.status_code, str(error))

    return ChatProviderError(str(error))
