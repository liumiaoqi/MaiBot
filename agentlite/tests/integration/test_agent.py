"""Integration tests for Agent class.

This module tests the Agent class with mocked providers to verify
core functionality without making real API calls.
"""

from __future__ import annotations

import pytest

from agentlite import Agent


@pytest.mark.integration
class TestAgentInitialization:
    """Tests for Agent initialization."""

    def test_agent_initialization(self, mock_provider):
        """Test basic agent creation."""
        agent = Agent(provider=mock_provider)

        assert agent.provider is mock_provider
        assert agent.system_prompt == "You are a helpful assistant."
        assert agent.max_iterations == 80
        assert agent.history == []

    def test_agent_with_custom_system_prompt(self, mock_provider):
        """Test agent creation with custom system prompt."""
        agent = Agent(provider=mock_provider, system_prompt="You are a specialized assistant.")

        assert agent.system_prompt == "You are a specialized assistant."

    def test_agent_with_tools(self, mock_provider, add_tool):
        """Test agent creation with tools."""
        agent = Agent(provider=mock_provider, tools=[add_tool])

        assert len(agent.tools.tools) == 1
        assert agent.tools.tools[0].name == "add"

    def test_agent_with_custom_max_iterations(self, mock_provider):
        """Test agent with custom max_iterations."""
        agent = Agent(provider=mock_provider, max_iterations=5)

        assert agent.max_iterations == 5


@pytest.mark.integration
class TestAgentRun:
    """Tests for Agent.run() method."""

    @pytest.mark.asyncio
    async def test_agent_run_simple(self, mock_provider):
        """Test simple non-streaming run."""
        mock_provider.add_text_response("Hello there!")
        agent = Agent(provider=mock_provider)

        response = await agent.run("Hi")

        assert response == "Hello there!"

    @pytest.mark.asyncio
    async def test_agent_run_adds_to_history(self, mock_provider):
        """Test that run adds messages to history."""
        mock_provider.add_text_response("Response!")
        agent = Agent(provider=mock_provider)

        await agent.run("Hello")

        # History should have user message and assistant response
        assert len(agent.history) == 2
        assert agent.history[0].role == "user"
        assert agent.history[0].extract_text() == "Hello"
        assert agent.history[1].role == "assistant"

    @pytest.mark.asyncio
    async def test_agent_run_multiple_messages(self, mock_provider):
        """Test multiple runs accumulate history."""
        mock_provider.add_text_responses("Response 1", "Response 2")
        agent = Agent(provider=mock_provider)

        await agent.run("Message 1")
        await agent.run("Message 2")

        # Should have 4 messages total
        assert len(agent.history) == 4
        assert agent.history[0].role == "user"
        assert agent.history[1].role == "assistant"
        assert agent.history[2].role == "user"
        assert agent.history[3].role == "assistant"

    @pytest.mark.asyncio
    async def test_agent_run_tracks_calls(self, mock_provider):
        """Test that provider.generate is called during run."""
        mock_provider.add_text_response("Response!")
        agent = Agent(provider=mock_provider)

        await agent.run("Hello")

        assert len(mock_provider.calls) == 1
        call = mock_provider.calls[0]
        assert call["system_prompt"] == "You are a helpful assistant."
        assert len(call["history"]) == 1  # User message


@pytest.mark.integration
class TestAgentGenerate:
    """Tests for Agent.generate() method."""

    @pytest.mark.asyncio
    async def test_agent_generate_returns_message(self, mock_provider):
        """Test that generate returns a Message."""
        mock_provider.add_text_response("Generated response")
        agent = Agent(provider=mock_provider)

        message = await agent.generate("Hello")

        assert message.role == "assistant"
        assert message.extract_text() == "Generated response"

    @pytest.mark.asyncio
    async def test_agent_generate_without_tool_loop(self, mock_provider):
        """Test that generate doesn't do tool calling loop."""
        # Add tool call response
        mock_provider.add_tool_call("add", {"a": 1, "b": 2}, "3")
        agent = Agent(provider=mock_provider, tools=[])

        message = await agent.generate("Calculate 1+2")

        # Should return the tool call without executing it
        assert message.has_tool_calls()
        assert len(message.tool_calls) == 1
        assert message.tool_calls[0].function.name == "add"

    @pytest.mark.asyncio
    async def test_agent_generate_adds_to_history(self, mock_provider):
        """Test that generate adds response to history."""
        mock_provider.add_text_response("Response!")
        agent = Agent(provider=mock_provider)

        await agent.generate("Hello")

        assert len(agent.history) == 2
        assert agent.history[1].role == "assistant"


@pytest.mark.integration
class TestAgentHistory:
    """Tests for Agent history management."""

    @pytest.mark.asyncio
    async def test_agent_history_property_returns_copy(self, mock_provider):
        """Test that history property returns a copy."""
        mock_provider.add_text_response("Response!")
        agent = Agent(provider=mock_provider)

        await agent.run("Hello")

        history = agent.history
        history.clear()  # Modify the copy

        # Original should still have messages
        assert len(agent.history) == 2

    @pytest.mark.asyncio
    async def test_agent_clear_history(self, mock_provider):
        """Test clearing history."""
        mock_provider.add_text_response("Response!")
        agent = Agent(provider=mock_provider)

        await agent.run("Hello")
        agent.clear_history()

        assert agent.history == []

    @pytest.mark.asyncio
    async def test_agent_add_message(self, mock_provider):
        """Test manually adding a message."""
        agent = Agent(provider=mock_provider)

        from agentlite import Message

        agent.add_message(Message(role="user", content="Manual message"))

        assert len(agent.history) == 1
        assert agent.history[0].extract_text() == "Manual message"


@pytest.mark.integration
class TestAgentWithTools:
    """Tests for Agent with tools."""

    @pytest.mark.asyncio
    async def test_agent_with_tools_initialization(self, mock_provider, add_tool):
        """Test agent initialization with tools."""
        agent = Agent(
            provider=mock_provider, tools=[add_tool], system_prompt="You have access to tools."
        )

        assert len(agent.tools.tools) == 1

        # Run to verify tools are passed to provider
        mock_provider.add_text_response("I have tools available")
        await agent.run("Hello")

        # Check that tools were passed to provider
        assert len(mock_provider.calls) == 1
        assert len(mock_provider.calls[0]["tools"]) == 1

    @pytest.mark.asyncio
    async def test_agent_tool_call_execution(self, mock_provider, add_tool):
        """Test that agent executes tool calls."""
        # First response: tool call
        mock_provider.add_tool_call("add", {"a": 1, "b": 2}, "3")
        # Second response: text after tool result
        mock_provider.add_text_response("The sum is 3")

        agent = Agent(provider=mock_provider, tools=[add_tool])

        response = await agent.run("What is 1+2?")

        assert "3" in response
        # Should have made 2 calls to provider
        assert len(mock_provider.calls) == 2


@pytest.mark.integration
class TestAgentMaxIterations:
    """Tests for max_iterations behavior."""

    @pytest.mark.asyncio
    async def test_agent_respects_max_iterations(self, mock_provider, add_tool):
        """Test that agent stops after max_iterations."""
        # Always return tool calls to trigger iteration limit
        for _ in range(10):
            mock_provider.add_tool_call("add", {"a": 1, "b": 2}, "3")

        agent = Agent(provider=mock_provider, tools=[add_tool], max_iterations=3)

        response = await agent.run("Calculate")

        # Should stop after max_iterations
        assert len(mock_provider.calls) <= 3
        assert "Maximum tool call iterations reached" in response

    @pytest.mark.asyncio
    async def test_agent_no_iterations_for_simple_response(self, mock_provider):
        """Test that simple responses don't count as iterations."""
        mock_provider.add_text_response("Simple response")
        agent = Agent(provider=mock_provider, max_iterations=1)

        response = await agent.run("Hello")

        assert response == "Simple response"


@pytest.mark.integration
class TestAgentStreaming:
    """Tests for streaming mode."""

    @pytest.mark.asyncio
    async def test_agent_run_streaming(self, mock_provider):
        """Test streaming run."""
        mock_provider.add_text_response("Streamed response")
        agent = Agent(provider=mock_provider)

        stream = await agent.run("Hello", stream=True)

        # Collect stream
        chunks = []
        async for chunk in stream:
            chunks.append(chunk)

        assert len(chunks) > 0
        assert "".join(chunks) == "Streamed response"

    @pytest.mark.asyncio
    async def test_agent_streaming_adds_to_history(self, mock_provider):
        """Test that streaming adds messages to history."""
        mock_provider.add_text_response("Response")
        agent = Agent(provider=mock_provider)

        stream = await agent.run("Hello", stream=True)
        async for _ in stream:
            pass

        assert len(agent.history) == 2
