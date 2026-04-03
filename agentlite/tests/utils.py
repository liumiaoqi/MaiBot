"""Test utilities and helpers for AgentLite tests.

This module provides utility functions and helpers used across test modules.
"""

from __future__ import annotations

import asyncio
from typing import Any, TypeVar

T = TypeVar("T")


async def run_async(coro: asyncio.Coroutine[Any, Any, T]) -> T:
    """Run an async coroutine and return the result.

    This is a helper for tests that need to run async code synchronously.

    Args:
        coro: The coroutine to run.

    Returns:
        The result of the coroutine.
    """
    return await coro


def run_sync(coro: asyncio.Coroutine[Any, Any, T]) -> T:
    """Run an async coroutine synchronously.

    Args:
        coro: The coroutine to run.

    Returns:
        The result of the coroutine.
    """
    return asyncio.run(coro)


async def collect_stream(stream) -> list[Any]:
    """Collect all items from an async stream into a list.

    Args:
        stream: The async stream to collect from.

    Returns:
        List of all items from the stream.
    """
    items = []
    async for item in stream:
        items.append(item)
    return items


async def collect_stream_text(stream) -> str:
    """Collect all text from an async text stream.

    Args:
        stream: The async stream to collect from.

    Returns:
        Concatenated text from all items.
    """
    from agentlite import TextPart

    text_parts = []
    async for item in stream:
        if isinstance(item, TextPart):
            text_parts.append(item.text)
        elif isinstance(item, str):
            text_parts.append(item)
    return "".join(text_parts)


def create_tool_schema(
    name: str,
    description: str,
    properties: dict[str, Any],
    required: list[str] | None = None,
) -> dict[str, Any]:
    """Create a JSON schema for a tool.

    Args:
        name: Tool name.
        description: Tool description.
        properties: JSON schema properties.
        required: List of required property names.

    Returns:
        JSON schema for the tool.
    """
    schema = {
        "type": "object",
        "properties": properties,
    }
    if required:
        schema["required"] = required
    return schema
