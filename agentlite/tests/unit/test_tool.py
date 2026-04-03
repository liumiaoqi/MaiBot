"""Unit tests for tool decorator and CallableTool.

This module tests the @tool() decorator and related tool functionality.
"""

from __future__ import annotations

import pytest

from agentlite.tool import tool, CallableTool, ToolOk, ToolError


class TestToolDecorator:
    """Tests for the @tool() decorator."""

    def test_tool_decorator_basic(self):
        """Test basic tool decorator functionality."""

        @tool()
        async def add(a: float, b: float) -> float:
            """Add two numbers."""
            return a + b

        assert isinstance(add, CallableTool)
        assert add.name == "add"
        assert add.description == "Add two numbers."
        assert add.parameters["type"] == "object"
        assert "a" in add.parameters["properties"]
        assert "b" in add.parameters["properties"]
        assert add.parameters["properties"]["a"]["type"] == "number"
        assert add.parameters["properties"]["b"]["type"] == "number"
        assert add.parameters["required"] == ["a", "b"]

    def test_tool_decorator_with_default_params(self):
        """Test tool decorator with default parameters."""

        @tool()
        async def greet(name: str, greeting: str = "Hello") -> str:
            """Greet someone."""
            return f"{greeting}, {name}!"

        assert greet.name == "greet"
        assert "name" in greet.parameters["required"]
        assert "greeting" not in greet.parameters["required"]

    def test_tool_decorator_custom_name(self):
        """Test tool decorator with custom name."""

        @tool(name="custom_add")
        async def add(a: float, b: float) -> float:
            """Add two numbers."""
            return a + b

        assert add.name == "custom_add"

    def test_tool_decorator_custom_description(self):
        """Test tool decorator with custom description."""

        @tool(description="Custom description")
        async def add(a: float, b: float) -> float:
            """Add two numbers."""
            return a + b

        assert add.description == "Custom description"

    def test_tool_decorator_no_docstring(self):
        """Test tool decorator with no docstring."""

        @tool()
        async def no_doc(a: float) -> float:
            return a

        assert no_doc.description == "No description provided"

    def test_tool_decorator_param_types(self):
        """Test tool decorator with various parameter types."""

        @tool()
        async def multi_types(
            s: str,
            i: int,
            f: float,
            b: bool,
        ) -> dict:
            """Multiple types."""
            return {"s": s, "i": i, "f": f, "b": b}

        props = multi_types.parameters["properties"]
        assert props["s"]["type"] == "string"
        assert props["i"]["type"] == "integer"
        assert props["f"]["type"] == "number"
        assert props["b"]["type"] == "boolean"

    def test_tool_decorator_no_type_hints(self):
        """Test tool decorator with no type hints."""

        @tool()
        async def no_types(param) -> str:
            """No type hints."""
            return str(param)

        assert no_types.parameters["properties"]["param"]["type"] == "string"


class TestToolDecoratorExecution:
    """Tests for tool decorator execution."""

    @pytest.mark.asyncio
    async def test_tool_execution_success(self):
        """Test successful tool execution."""

        @tool()
        async def add(a: float, b: float) -> float:
            """Add two numbers."""
            return a + b

        result = await add(1.0, 2.0)
        assert isinstance(result, ToolOk)
        assert result.output == "3.0"

    @pytest.mark.asyncio
    async def test_tool_execution_error(self):
        """Test tool execution with error."""

        @tool()
        async def divide(a: float, b: float) -> float:
            """Divide two numbers."""
            return a / b

        result = await divide(1.0, 0.0)
        assert isinstance(result, ToolError)
        assert "division by zero" in result.message

    @pytest.mark.asyncio
    async def test_tool_execution_with_kwargs(self):
        """Test tool execution with keyword arguments."""

        @tool()
        async def greet(name: str, greeting: str = "Hello") -> str:
            """Greet someone."""
            return f"{greeting}, {name}!"

        result = await greet(name="World", greeting="Hi")
        assert isinstance(result, ToolOk)
        assert result.output == "Hi, World!"


class TestToolDecoratorMemorixBug:
    """Tests for the specific bug reported by Memorix project."""

    def test_tool_decorator_memorix_case(self):
        """Test the exact case from Memorix bug report.

        This test verifies that the @tool() decorator works correctly
        with async functions that have string and float parameters.
        """

        @tool()
        async def add_memory(content: str, importance: float = 0.5) -> dict:
            """存储记忆"""
            return {"status": "ok"}

        assert isinstance(add_memory, CallableTool)
        assert add_memory.name == "add_memory"
        assert add_memory.description == "存储记忆"

        # Check parameters schema
        params = add_memory.parameters
        assert params["type"] == "object"
        assert "content" in params["properties"]
        assert "importance" in params["properties"]
        assert params["properties"]["content"]["type"] == "string"
        assert params["properties"]["importance"]["type"] == "number"

        # content is required (no default), importance is optional
        assert "content" in params["required"]
        assert "importance" not in params["required"]

    @pytest.mark.asyncio
    async def test_tool_decorator_memorix_execution(self):
        """Test execution of the Memorix case."""

        @tool()
        async def add_memory(content: str, importance: float = 0.5) -> dict:
            """存储记忆"""
            return {"status": "ok", "content": content, "importance": importance}

        result = await add_memory("test content", 0.8)
        assert isinstance(result, ToolOk)
        assert "ok" in result.output

    def test_tool_decorator_can_be_used_in_agent(self):
        """Test that decorated tools can be used with Agent.

        This is an integration-style test to ensure the decorated tool
        has all required attributes for Agent usage.
        """
        from agentlite import Agent, OpenAIProvider

        @tool()
        async def add_memory(content: str, importance: float = 0.5) -> dict:
            """存储记忆"""
            return {"status": "ok"}

        # Verify the tool has the base property required by Agent
        assert hasattr(add_memory, "base")
        base_tool = add_memory.base
        assert base_tool.name == "add_memory"
        assert base_tool.description == "存储记忆"
        assert base_tool.parameters == add_memory.parameters
