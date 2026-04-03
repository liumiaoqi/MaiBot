"""Test configuration and shared fixtures for AgentLite tests.

This module provides pytest configuration and fixtures that are shared
across all test modules.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Sequence
from typing import Any, Optional

import pytest

from agentlite import (
    Agent,
    ContentPart,
    Message,
    TextPart,
    ToolCall,
    ToolOk,
    ToolError,
    tool,
)
from agentlite.provider import ChatProvider, StreamedMessage, TokenUsage
from agentlite.tool import Tool, ToolResult


# =============================================================================
# pytest Configuration
# =============================================================================


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "scenario: Real-world scenario tests")
    config.addinivalue_line("markers", "slow: Slow tests that may take time")


# =============================================================================
# Mock Provider Implementation
# =============================================================================


class MockStreamedMessage:
    """Mock streamed message for testing."""

    def __init__(self, parts: list[ContentPart]):
        self._parts = parts
        self._id = "mock-msg-123"
        self._usage = TokenUsage(input_tokens=10, output_tokens=5)

    def __aiter__(self) -> AsyncIterator[ContentPart]:
        """Return async iterator over parts."""
        return self._iter_parts()

    async def _iter_parts(self) -> AsyncIterator[ContentPart]:
        """Iterate over parts."""
        for part in self._parts:
            yield part

    @property
    def id(self) -> Optional[str]:
        """Message ID."""
        return self._id

    @property
    def usage(self) -> Optional[TokenUsage]:
        """Token usage."""
        return self._usage


class MockProvider:
    """Mock provider for testing AgentLite without real API calls.

    This provider simulates OpenAI API responses and allows:
    - Configuring response sequences
    - Simulating tool calls
    - Simulating errors
    - Tracking all calls for verification

    Example:
        provider = MockProvider()
        provider.add_text_response("Hello!")
        provider.add_tool_call("add", {"a": 1, "b": 2}, "3")

        agent = Agent(provider=provider)
        response = await agent.run("Hi")

        # Verify calls
        assert len(provider.calls) == 1
        assert provider.calls[0]["system_prompt"] == "You are helpful."
    """

    def __init__(self):
        self.responses: list[dict[str, Any]] = []
        self.calls: list[dict[str, Any]] = []
        self.model = "mock-model"

    def add_text_response(self, text: str) -> None:
        """Add a text response to the queue."""
        self.responses.append({"type": "text", "content": text})

    def add_text_responses(self, *texts: str) -> None:
        """Add multiple text responses to the queue."""
        for text in texts:
            self.add_text_response(text)

    def add_tool_call(self, name: str, arguments: dict[str, Any], result: str) -> None:
        """Add a tool call response to the queue."""
        self.responses.append(
            {"type": "tool_call", "name": name, "arguments": arguments, "result": result}
        )

    def add_tool_calls(self, calls: list[dict[str, Any]]) -> None:
        """Add multiple tool calls to the queue."""
        for call in calls:
            self.add_tool_call(call["name"], call["arguments"], call.get("result", ""))

    def add_error(self, error: Exception) -> None:
        """Add an error response to the queue."""
        self.responses.append({"type": "error", "error": error})

    def clear_responses(self) -> None:
        """Clear all pending responses."""
        self.responses.clear()

    @property
    def model_name(self) -> str:
        """Model name."""
        return self.model

    async def generate(
        self,
        system_prompt: str,
        tools: Sequence[Tool],
        history: Sequence[Message],
    ) -> StreamedMessage:
        """Generate a mock response."""
        self.calls.append(
            {
                "system_prompt": system_prompt,
                "tools": list(tools),
                "history": list(history),
            }
        )

        if not self.responses:
            return MockStreamedMessage([TextPart(text="Mock response")])

        response = self.responses.pop(0)

        if response["type"] == "error":
            raise response["error"]
        elif response["type"] == "text":
            return MockStreamedMessage([TextPart(text=response["content"])])
        elif response["type"] == "tool_call":
            return MockStreamedMessage(
                [
                    ToolCall(
                        id="call_123",
                        function=ToolCall.FunctionBody(
                            name=response["name"], arguments=json.dumps(response["arguments"])
                        ),
                    )
                ]
            )
        else:
            return MockStreamedMessage([TextPart(text="Unknown response type")])


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_provider():
    """Create a mock provider with no responses configured."""
    return MockProvider()


@pytest.fixture
def mock_provider_with_response():
    """Create a mock provider that returns a simple text response."""
    provider = MockProvider()
    provider.add_text_response("Hello!")
    return provider


@pytest.fixture
def mock_provider_with_sequence():
    """Create a mock provider with multiple responses configured."""
    provider = MockProvider()
    provider.add_text_responses("Response 1", "Response 2", "Response 3")
    return provider


# =============================================================================
# Message Fixtures
# =============================================================================


@pytest.fixture
def sample_text_message():
    """Create a sample text message."""
    return Message(role="user", content="Hello!")


@pytest.fixture
def sample_assistant_message():
    """Create a sample assistant message."""
    return Message(role="assistant", content="Hi there!")


@pytest.fixture
def sample_tool_call():
    """Create a sample tool call."""
    return ToolCall(
        id="call_123", function=ToolCall.FunctionBody(name="add", arguments='{"a": 1, "b": 2}')
    )


@pytest.fixture
def sample_tool_message():
    """Create a sample tool response message."""
    return Message(role="tool", content="3", tool_call_id="call_123")


# =============================================================================
# Tool Fixtures
# =============================================================================


@pytest.fixture
def add_tool():
    """Create a simple add tool."""

    @tool()
    async def add(a: float, b: float) -> float:
        """Add two numbers."""
        return a + b

    return add


@pytest.fixture
def multiply_tool():
    """Create a multiply tool."""

    @tool()
    async def multiply(a: float, b: float) -> float:
        """Multiply two numbers."""
        return a * b

    return multiply


@pytest.fixture
def error_tool():
    """Create a tool that raises an error."""

    @tool()
    async def error() -> str:
        """Always raises an error."""
        raise ValueError("Test error")

    return error


@pytest.fixture
def slow_tool():
    """Create a tool that takes some time."""

    @tool()
    async def slow_operation(duration: float = 0.1) -> str:
        """Simulate a slow operation."""
        await asyncio.sleep(duration)
        return f"Completed after {duration}s"

    return slow_operation


# =============================================================================
# Agent Fixtures
# =============================================================================


@pytest.fixture
async def simple_agent(mock_provider):
    """Create a simple agent with mocked provider."""
    return Agent(provider=mock_provider)


@pytest.fixture
async def agent_with_tools(mock_provider, add_tool):
    """Create an agent with tools."""
    return Agent(provider=mock_provider, tools=[add_tool])


@pytest.fixture
async def agent_with_multiple_tools(mock_provider, add_tool, multiply_tool):
    """Create an agent with multiple tools."""
    return Agent(provider=mock_provider, tools=[add_tool, multiply_tool])


# =============================================================================
# Utility Fixtures
# =============================================================================


@pytest.fixture
def sample_conversation():
    """Create a sample conversation history."""
    return [
        Message(role="user", content="Hello!"),
        Message(role="assistant", content="Hi there! How can I help?"),
        Message(role="user", content="What is 2+2?"),
        Message(role="assistant", content="2+2=4"),
    ]


@pytest.fixture
def event_loop():
    """Create an instance of the default event loop for each test case."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
