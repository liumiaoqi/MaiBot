"""Main Agent class for AgentLite.

This module provides the core Agent class that orchestrates LLM interactions,
tool calling, and conversation management.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from typing import TYPE_CHECKING, Any, Optional

from agentlite.message import (
    ContentPart,
    Message,
    TextPart,
    ToolCall,
    ToolCallPart,
)
from agentlite.provider import ChatProvider, StreamedMessage, TokenUsage
from agentlite.tool import SimpleToolset, Tool, ToolResult, ToolType
from agentlite.labor_market import LaborMarket

if TYPE_CHECKING:
    pass


class Agent:
    """An LLM agent that can use tools and maintain conversation history.

    The Agent class is the main interface for interacting with LLMs. It handles:
    - Sending messages to the LLM
    - Managing tool calls and execution
    - Maintaining conversation history
    - Streaming responses

    Attributes:
        provider: The LLM provider to use.
        system_prompt: The system prompt for the agent.
        tools: The toolset containing available tools.
        history: The conversation history.

    Example:
        >>> provider = OpenAIProvider(api_key="sk-...", model="gpt-4")
        >>> agent = Agent(
        ...     provider=provider,
        ...     system_prompt="You are a helpful assistant.",
        ... )
        >>> response = await agent.run("Hello!")
        >>> print(response)
    """

    def __init__(
        self,
        provider: ChatProvider,
        system_prompt: str = "You are a helpful assistant.",
        tools: Sequence[ToolType] | None = None,
        max_iterations: int = 80,
        labor_market: LaborMarket | None = None,
        name: str = "agent",
        allow_subagents: bool = False,
    ):
        """Initialize the agent.

        Args:
            provider: The LLM provider to use.
            system_prompt: The system prompt for the agent.
            tools: Optional sequence of tools to make available.
            max_iterations: Maximum number of tool call iterations per request.
            labor_market: Optional LaborMarket for managing subagents.
            name: Name of the agent (for identification in subagent hierarchies).
            allow_subagents: Whether this agent is allowed to register subagents.
        """
        self.provider = provider
        self.system_prompt = system_prompt
        self.tools = SimpleToolset(tools)
        self.max_iterations = max_iterations
        self.labor_market = labor_market or LaborMarket()
        self.name = name
        self.allow_subagents = allow_subagents
        self._history: list[Message] = []

    @property
    def history(self) -> list[Message]:
        """Get the conversation history.

        Returns:
            A copy of the conversation history.
        """
        return self._history.copy()

    def clear_history(self) -> None:
        """Clear the conversation history."""
        self._history.clear()

    def add_message(self, message: Message) -> None:
        """Add a message to the history.

        Args:
            message: The message to add.
        """
        self._history.append(message)

    async def run(
        self,
        message: str,
        *,
        stream: bool = False,
    ) -> str | AsyncIterator[str]:
        """Run the agent with a user message.

        This method sends the message to the LLM and handles any tool calls
        that the model requests. It continues the conversation until the
        model produces a final response without tool calls.

        Args:
            message: The user message.
            stream: Whether to stream the response.

        Returns:
            If stream=False: The complete response as a string.
            If stream=True: An async iterator yielding response chunks.

        Example:
            # Non-streaming
            >>> response = await agent.run("What is 2 + 2?")
            >>> print(response)

            # Streaming
            >>> async for chunk in await agent.run("Tell me a story", stream=True):
            ...     print(chunk, end="")
        """
        # Add user message to history
        self._history.append(Message(role="user", content=message))

        if stream:
            return self._run_streaming()
        else:
            return await self._run_non_streaming()

    async def _run_non_streaming(self) -> str:
        """Run the agent in non-streaming mode.

        Returns:
            The complete response as a string.
        """
        iterations = 0
        tool_calls: list[ToolCall] = []

        while iterations < self.max_iterations:
            iterations += 1

            # Generate response
            stream = await self.provider.generate(
                system_prompt=self.system_prompt,
                tools=self.tools.tools,
                history=self._history,
            )

            # Collect response parts
            response_parts: list[ContentPart] = []
            tool_calls: list[ToolCall] = []

            async for part in stream:
                if isinstance(part, ToolCall):
                    tool_calls.append(part)
                elif isinstance(part, ToolCallPart):
                    if tool_calls:
                        tool_calls[-1].merge_in_place(part)
                elif isinstance(part, ContentPart):
                    response_parts.append(part)

            # Extract text from response
            response_text = ""
            for part in response_parts:
                if isinstance(part, TextPart):
                    response_text += part.text

            # Add assistant message to history
            self._history.append(
                Message(
                    role="assistant",
                    content=response_parts,
                    tool_calls=tool_calls if tool_calls else None,
                )
            )

            # If no tool calls, we're done
            if not tool_calls:
                return response_text

            # Execute tool calls
            tool_results = await self._execute_tool_calls(tool_calls)

            # Add tool results to history
            for result in tool_results:
                self._history.append(
                    Message(
                        role="tool",
                        content=result.output,
                        tool_call_id=result.tool_call_id,
                    )
                )

        # Max iterations reached
        last_tools_msg = ""
        try:
            if tool_calls:
                tool_names = [tc.function.name for tc in tool_calls if hasattr(tc, "function")]
                if tool_names:
                    last_tools_msg = f" Last tools called: {', '.join(tool_names)}."
        except Exception:
            pass

        return (
            f"Maximum tool call iterations reached ({self.max_iterations})."
            f"{last_tools_msg}"
            f" Consider increasing max_iterations or breaking the task into smaller steps."
        )

    async def _run_streaming(self) -> AsyncIterator[str]:
        """Run the agent in streaming mode.

        Yields:
            Response text chunks.
        """
        iterations = 0
        tool_calls: list[ToolCall] = []

        while iterations < self.max_iterations:
            iterations += 1

            # Generate response
            stream = await self.provider.generate(
                system_prompt=self.system_prompt,
                tools=self.tools.tools,
                history=self._history,
            )

            # Collect response parts and yield text
            response_parts: list[ContentPart] = []
            tool_calls: list[ToolCall] = []

            async for part in stream:
                if isinstance(part, ToolCall):
                    tool_calls.append(part)
                elif isinstance(part, ToolCallPart):
                    if tool_calls:
                        tool_calls[-1].merge_in_place(part)
                elif isinstance(part, ContentPart):
                    response_parts.append(part)
                    if isinstance(part, TextPart):
                        yield part.text

            # Add assistant message to history
            self._history.append(
                Message(
                    role="assistant",
                    content=response_parts,
                    tool_calls=tool_calls if tool_calls else None,
                )
            )

            # If no tool calls, we're done
            if not tool_calls:
                return

            # Execute tool calls
            tool_results = await self._execute_tool_calls(tool_calls)

            # Add tool results to history
            for result in tool_results:
                self._history.append(
                    Message(
                        role="tool",
                        content=result.output,
                        tool_call_id=result.tool_call_id,
                    )
                )

        # Max iterations reached
        last_tools_msg = ""
        try:
            if tool_calls:
                tool_names = [tc.function.name for tc in tool_calls if hasattr(tc, "function")]
                if tool_names:
                    last_tools_msg = f" Last tools called: {', '.join(tool_names)}."
        except Exception:
            pass

        yield (
            f"Maximum tool call iterations reached ({self.max_iterations})."
            f"{last_tools_msg}"
            f" Consider increasing max_iterations or breaking the task into smaller steps."
        )

    async def _execute_tool_calls(
        self,
        tool_calls: list[ToolCall],
    ) -> list[_ToolResult]:
        """Execute a list of tool calls.

        Args:
            tool_calls: The tool calls to execute.

        Returns:
            List of tool results.
        """
        results: list[_ToolResult] = []

        # Execute all tool calls concurrently
        futures = [self.tools.handle(tc) for tc in tool_calls]

        for tc, future in zip(tool_calls, futures):
            try:
                if asyncio.isfuture(future):
                    result = await future
                else:
                    result = future

                results.append(
                    _ToolResult(
                        tool_call_id=tc.id,
                        output=result.output if isinstance(result, ToolResult) else str(result),
                        is_error=result.is_error if isinstance(result, ToolResult) else False,
                    )
                )
            except Exception as e:
                results.append(
                    _ToolResult(
                        tool_call_id=tc.id,
                        output=str(e),
                        is_error=True,
                    )
                )

        return results

    async def generate(
        self,
        message: str,
    ) -> Message:
        """Generate a single response without tool calling loop.

        This method sends a message to the LLM and returns the response
        without executing any tool calls. This is useful when you want
        to handle tool calls manually.

        Args:
            message: The user message.

        Returns:
            The assistant's response message.
        """
        # Add user message to history
        self._history.append(Message(role="user", content=message))

        # Generate response
        stream = await self.provider.generate(
            system_prompt=self.system_prompt,
            tools=self.tools.tools,
            history=self._history,
        )

        # Collect response parts
        response_parts: list[ContentPart] = []
        tool_calls: list[ToolCall] = []

        async for part in stream:
            if isinstance(part, ToolCall):
                tool_calls.append(part)
            elif isinstance(part, ToolCallPart):
                if tool_calls:
                    tool_calls[-1].merge_in_place(part)
            elif isinstance(part, ContentPart):
                response_parts.append(part)

        # Create response message
        response = Message(
            role="assistant",
            content=response_parts,
            tool_calls=tool_calls if tool_calls else None,
        )

        # Add to history
        self._history.append(response)

        return response

    def add_subagent(
        self,
        name: str,
        agent: Agent,
        description: str,
        dynamic: bool = False,
    ) -> None:
        """Add a subagent to this agent's labor market.

        Args:
            name: Unique name for the subagent
            agent: The Agent instance to add
            description: Description of what the subagent does
            dynamic: If True, add as dynamic subagent; otherwise fixed
        """
        if not self.allow_subagents:
            raise RuntimeError("Subagent delegation is disabled for this agent runtime.")

        if dynamic:
            self.labor_market.add_dynamic_subagent(name, agent)
        else:
            self.labor_market.add_fixed_subagent(name, agent, description)

    def get_subagent(self, name: str) -> Agent | None:
        """Get a subagent by name.

        Args:
            name: Name of the subagent

        Returns:
            The subagent Agent if found, None otherwise
        """
        return self.labor_market.get_subagent(name)

    def create_subagent_copy(self) -> Agent:
        """Create a copy of this agent for use as a subagent.

        The copy will have:
        - Same provider
        - Independent history (empty)
        - Empty labor market (subagents cannot have their own subagents by default)

        Returns:
            A new Agent instance configured as a subagent
        """
        return Agent(
            provider=self.provider,
            system_prompt=self.system_prompt,
            tools=list(self.tools._tools.values()),
            max_iterations=self.max_iterations,
            labor_market=LaborMarket(),  # Empty labor market
            allow_subagents=False,
            name=f"{self.name}_sub",
        )


class _ToolResult:
    """Internal class for tool execution results."""

    def __init__(self, tool_call_id: str, output: str, is_error: bool):
        self.tool_call_id = tool_call_id
        self.output = output
        self.is_error = is_error
