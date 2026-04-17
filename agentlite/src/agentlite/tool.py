"""Tool system for AgentLite.

This module provides the tool abstraction layer for defining and executing
tools that can be called by LLM agents.
"""

from __future__ import annotations

import asyncio
import inspect
import json
from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Optional,
    Protocol,
    TypeVar,
    Union,
    Generic,
    get_type_hints,
)

import jsonschema
from pydantic import BaseModel, ValidationError

from agentlite.message import ToolCall

if TYPE_CHECKING:
    pass


class ToolResult(BaseModel):
    """The result of a tool execution.

    Attributes:
        output: The output of the tool (string or structured data).
        is_error: Whether the tool execution resulted in an error.
        message: A message describing the result (for model consumption).

    Example:
        >>> result = ToolOk(output="42")
        >>> print(result.output)
        42
    """

    output: str
    """The output of the tool execution."""

    is_error: bool = False
    """Whether the execution resulted in an error."""

    message: str = ""
    """A message describing the result (for model consumption)."""


class ToolOk(ToolResult):
    """Successful tool execution result.

    Example:
        >>> return ToolOk(output="File created successfully")
    """

    def __init__(self, output: str, message: str = ""):
        super().__init__(output=output, is_error=False, message=message or output)


class ToolError(ToolResult):
    """Failed tool execution result.

    Example:
        >>> return ToolError(message="File not found")
    """

    def __init__(self, message: str, output: str = ""):
        super().__init__(output=output or message, is_error=True, message=message)


class Tool(BaseModel):
    """Definition of a tool that can be called by the model.

    Attributes:
        name: The name of the tool.
        description: A description of what the tool does.
        parameters: JSON Schema for the tool parameters.

    Example:
        >>> tool = Tool(
        ...     name="add",
        ...     description="Add two numbers",
        ...     parameters={
        ...         "type": "object",
        ...         "properties": {
        ...             "a": {"type": "number"},
        ...             "b": {"type": "number"},
        ...         },
        ...         "required": ["a", "b"],
        ...     },
        ... )
    """

    name: str
    """The name of the tool."""

    description: str
    """A description of what the tool does."""

    parameters: dict[str, Any]
    """JSON Schema for the tool parameters."""

    def __init__(self, **data: Any):
        super().__init__(**data)
        # Validate the JSON schema
        try:
            jsonschema.validate(self.parameters, jsonschema.Draft202012Validator.META_SCHEMA)
        except jsonschema.ValidationError as e:
            raise ValueError(f"Invalid JSON schema for tool {self.name}: {e}") from e

    @property
    def base(self) -> "Tool":
        """Get the base Tool definition (returns self for Tool instances)."""
        return self


class CallableTool(Tool, ABC):
    """Abstract base class for callable tools.

    Subclasses must implement the __call__ method to define the tool's behavior.

    Example:
        >>> class AddTool(CallableTool):
        ...     name = "add"
        ...     description = "Add two numbers"
        ...     parameters = {
        ...         "type": "object",
        ...         "properties": {
        ...             "a": {"type": "number"},
        ...             "b": {"type": "number"},
        ...         },
        ...         "required": ["a", "b"],
        ...     }
        ...
        ...     async def __call__(self, a: float, b: float) -> ToolResult:
        ...         return ToolOk(output=str(a + b))
    """

    @abstractmethod
    async def __call__(self, *args: Any, **kwargs: Any) -> ToolResult:
        """Execute the tool.

        Args:
            *args: Positional arguments.
            **kwargs: Keyword arguments.

        Returns:
            The result of the tool execution.
        """
        ...

    @property
    def base(self) -> "Tool":
        """Get the base Tool definition."""
        return Tool(
            name=self.name,
            description=self.description,
            parameters=self.parameters,
        )

    async def call(self, arguments: dict[str, Any]) -> ToolResult:
        """Call the tool with validated arguments.

        Args:
            arguments: The arguments to pass to the tool.

        Returns:
            The result of the tool execution.
        """
        # Validate arguments against schema
        try:
            jsonschema.validate(arguments, self.parameters)
        except jsonschema.ValidationError as e:
            return ToolError(message=f"Invalid arguments: {e}")

        # Call the tool
        try:
            if isinstance(arguments, list):
                result = await self.__call__(*arguments)
            elif isinstance(arguments, dict):
                result = await self.__call__(**arguments)
            else:
                result = await self.__call__(arguments)

            if not isinstance(result, ToolResult):
                return ToolError(message=f"Tool returned invalid type: {type(result)}")
            return result
        except Exception as e:
            return ToolError(message=f"Tool execution failed: {e}")


Params = TypeVar("Params", bound=BaseModel)


class CallableTool2(ABC, Generic[Params]):
    """Type-safe callable tool using Pydantic models for parameters.

    This is the preferred way to define tools as it provides full type safety
    and automatic JSON schema generation.

    Example:
        >>> class AddParams(BaseModel):
        ...     a: float
        ...     b: float
        >>> class AddTool(CallableTool2[AddParams]):
        ...     name = "add"
        ...     description = "Add two numbers"
        ...     params = AddParams
        ...
        ...     async def __call__(self, params: AddParams) -> ToolResult:
        ...         return ToolOk(output=str(params.a + params.b))
    """

    name: str
    """The name of the tool."""

    description: str
    """A description of what the tool does."""

    params: type[Params]
    """The Pydantic model class for parameters."""

    def __init__(
        self,
        name: str | None = None,
        description: str | None = None,
        params: type[Params] | None = None,
    ):
        cls = self.__class__

        self.name = name or getattr(cls, "name", "")
        if not self.name:
            raise ValueError("Tool name must be provided")

        self.description = description or getattr(cls, "description", "")
        if not self.description:
            raise ValueError("Tool description must be provided")

        self.params = params or getattr(cls, "params", None)
        if self.params is None:
            raise ValueError("Tool params must be provided")

        # Generate JSON schema from Pydantic model
        self._schema = self.params.model_json_schema()

    @property
    def base(self) -> Tool:
        """Get the base Tool definition."""
        return Tool(
            name=self.name,
            description=self.description,
            parameters=self._schema,
        )

    @abstractmethod
    async def __call__(self, params: Params) -> ToolResult:
        """Execute the tool.

        Args:
            params: The validated parameters.

        Returns:
            The result of the tool execution.
        """
        ...

    async def call(self, arguments: dict[str, Any]) -> ToolResult:
        """Call the tool with validated arguments.

        Args:
            arguments: The arguments to validate and pass to the tool.

        Returns:
            The result of the tool execution.
        """
        try:
            params = self.params.model_validate(arguments)
        except ValidationError as e:
            return ToolError(message=f"Invalid arguments: {e}")

        try:
            result = await self.__call__(params)
            if not isinstance(result, ToolResult):
                return ToolError(message=f"Tool returned invalid type: {type(result)}")
            return result
        except Exception as e:
            return ToolError(message=f"Tool execution failed: {e}")


class Toolset(Protocol):
    """Protocol for tool collections.

    A Toolset manages a collection of tools and handles tool calls.
    """

    @property
    def tools(self) -> list[Tool]:
        """Get all tool definitions."""
        ...

    def handle(self, tool_call: ToolCall) -> "ToolResult | asyncio.Future[ToolResult]":
        """Handle a tool call.

        Args:
            tool_call: The tool call to handle.

        Returns:
            The tool result or a future that resolves to the result.
        """
        ...


ToolType = Union[CallableTool, CallableTool2[Any]]


class SimpleToolset:
    """A simple in-memory toolset.

    This is the default toolset implementation that stores tools in a dictionary
    and executes them concurrently.

    Example:
        >>> toolset = SimpleToolset()
        >>> toolset.add(MyTool())
        >>> result = await toolset.handle(tool_call)
    """

    def __init__(self, tools: Iterable[ToolType] | None = None):
        """Initialize the toolset.

        Args:
            tools: Optional initial tools to add.
        """
        self._tools: dict[str, ToolType] = {}
        if tools:
            for tool in tools:
                self.add(tool)

    def add(self, tool: ToolType) -> "SimpleToolset":
        """Add a tool to the toolset.

        Args:
            tool: The tool to add.

        Returns:
            Self for chaining.

        Raises:
            ValueError: If a tool with the same name already exists.
        """
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' already exists")
        self._tools[tool.name] = tool
        return self

    def remove(self, name: str) -> "SimpleToolset":
        """Remove a tool from the toolset.

        Args:
            name: The name of the tool to remove.

        Returns:
            Self for chaining.

        Raises:
            KeyError: If the tool doesn't exist.
        """
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' not found")
        del self._tools[name]
        return self

    def get(self, name: str) -> ToolType | None:
        """Get a tool by name.

        Args:
            name: The name of the tool.

        Returns:
            The tool if found, None otherwise.
        """
        return self._tools.get(name)

    def __contains__(self, name: str) -> bool:
        """Check if a tool exists in the toolset."""
        return name in self._tools

    def __len__(self) -> int:
        """Get the number of tools in the toolset."""
        return len(self._tools)

    @property
    def tools(self) -> list[Tool]:
        """Get all tool definitions."""
        result = []
        for tool in self._tools.values():
            if isinstance(tool, CallableTool):
                result.append(
                    Tool(
                        name=tool.name,
                        description=tool.description,
                        parameters=tool.parameters,
                    )
                )
            else:
                result.append(tool.base)
        return result

    def handle(self, tool_call: ToolCall) -> "asyncio.Future[ToolResult]":
        """Handle a tool call.

        Args:
            tool_call: The tool call to handle.

        Returns:
            A future that resolves to the tool result.
        """
        tool = self._tools.get(tool_call.function.name)
        if tool is None:
            future: asyncio.Future[ToolResult] = asyncio.get_event_loop().create_future()
            future.set_result(ToolError(message=f"Tool '{tool_call.function.name}' not found"))
            return future

        # Parse arguments
        try:
            arguments = json.loads(tool_call.function.arguments or "{}")
        except json.JSONDecodeError as e:
            future = asyncio.get_event_loop().create_future()
            future.set_result(ToolError(message=f"Invalid JSON arguments: {e}"))
            return future

        # Execute tool
        async def _execute() -> ToolResult:
            try:
                return await tool.call(arguments)
            except Exception as e:
                return ToolError(message=f"Tool execution failed: {e}")

        return asyncio.create_task(_execute())


def tool(
    name: Optional[str] = None,
    description: Optional[str] = None,
) -> Callable[[Callable[..., Any]], CallableTool]:
    """Decorator to convert a function into a tool.

    This decorator automatically generates the JSON schema from the function's
    type hints and docstring.

    Args:
        name: Optional tool name (defaults to function name).
        description: Optional description (defaults to function docstring).

    Returns:
        A decorator that converts the function into a CallableTool.

    Example:
        >>> @tool()
        ... async def add(a: float, b: float) -> float:
        ...     '''Add two numbers.'''
        ...     return a + b
        >>> agent = Agent(tools=[add])
    """

    def decorator(func: callable) -> CallableTool:
        sig = inspect.signature(func)
        try:
            type_hints = get_type_hints(func)
        except Exception:
            type_hints = {}

        properties = {}
        required = []

        for param_name, param in sig.parameters.items():
            if param.default is inspect.Parameter.empty:
                required.append(param_name)

            param_type = type_hints.get(param_name, param.annotation)
            if param_type is inspect.Parameter.empty or param_type is None:
                param_type = str

            # Map Python types to JSON schema types
            if param_type in (str,):
                properties[param_name] = {"type": "string"}
            elif param_type in (int,):
                properties[param_name] = {"type": "integer"}
            elif param_type in (float,):
                properties[param_name] = {"type": "number"}
            elif param_type in (bool,):
                properties[param_name] = {"type": "boolean"}
            else:
                properties[param_name] = {"type": "string"}

        parameters = {
            "type": "object",
            "properties": properties,
        }
        if required:
            parameters["required"] = required

        # Create tool class
        tool_name = name or func.__name__
        tool_description = description or (func.__doc__ or "No description provided")
        tool_parameters = parameters

        class FunctionTool(CallableTool):
            name: str = tool_name
            description: str = tool_description
            parameters: dict[str, Any] = tool_parameters

            async def __call__(self, *args: Any, **kwargs: Any) -> ToolResult:
                try:
                    result = await func(*args, **kwargs)
                    return ToolOk(output=str(result))
                except Exception as e:
                    return ToolError(message=str(e))

        return FunctionTool()

    return decorator
