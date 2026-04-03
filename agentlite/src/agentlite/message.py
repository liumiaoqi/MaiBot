"""Core message types for AgentLite.

This module defines the message and content part types used throughout
AgentLite for communication with LLM providers.
"""

from __future__ import annotations

from abc import ABC
from typing import Any, ClassVar, Literal, Optional, Union, cast

from pydantic import BaseModel, GetCoreSchemaHandler, field_validator
from pydantic_core import core_schema


Role = Literal["system", "user", "assistant", "tool"]


class MergeableMixin:
    """Mixin for content parts that can be merged during streaming."""

    def merge_in_place(self, other: Any) -> bool:
        """Merge another part into this one.

        Args:
            other: The part to merge into this one.

        Returns:
            True if the merge was successful, False otherwise.
        """
        return False


class ContentPart(BaseModel, ABC, MergeableMixin):
    """Base class for message content parts.

    ContentPart uses a registry pattern to allow polymorphic validation
    of content part subclasses based on the 'type' field.

    Example:
        >>> text = TextPart(text="Hello")
        >>> print(text.model_dump())
        {'type': 'text', 'text': 'Hello'}
    """

    __content_part_registry: ClassVar[dict[str, type["ContentPart"]]] = {}

    type: str

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)

        type_value = getattr(cls, "type", None)
        if type_value is None or not isinstance(type_value, str):
            raise ValueError(
                f"ContentPart subclass {cls.__name__} must have a 'type' field of type str"
            )

        cls.__content_part_registry[type_value] = cls

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        """Custom schema for polymorphic ContentPart validation."""
        if cls.__name__ == "ContentPart":

            def validate_content_part(value: Any) -> Any:
                """Validate a value as a ContentPart subclass."""
                # Already an instance
                if hasattr(value, "__class__") and issubclass(value.__class__, cls):
                    return value

                # Dict with type field - dispatch to subclass
                if isinstance(value, dict) and "type" in value:
                    type_value = cast(dict[str, Any], value).get("type")
                    if not isinstance(type_value, str):
                        raise ValueError(f"Cannot validate {value} as ContentPart")
                    target_class = cls.__content_part_registry.get(type_value)
                    if target_class is None:
                        raise ValueError(f"Unknown content part type: {type_value}")
                    return target_class.model_validate(value)

                raise ValueError(f"Cannot validate {value} as ContentPart")

            return core_schema.no_info_plain_validator_function(validate_content_part)

        # For subclasses, use default schema
        return handler(source_type)


class TextPart(ContentPart):
    """Text content part.

    Attributes:
        text: The text content.

    Example:
        >>> part = TextPart(text="Hello, world!")
        >>> part.model_dump()
        {'type': 'text', 'text': 'Hello, world!'}
    """

    type: str = "text"
    text: str

    def merge_in_place(self, other: Any) -> bool:
        """Merge another TextPart into this one."""
        if not isinstance(other, TextPart):
            return False
        self.text += other.text
        return True


class ImageURLPart(ContentPart):
    """Image URL content part.

    Attributes:
        image_url: The image URL configuration.

    Example:
        >>> part = ImageURLPart(
        ...     image_url=ImageURLPart.ImageURL(url="https://example.com/image.png")
        ... )
    """

    class ImageURL(BaseModel):
        """Image URL configuration."""

        url: str
        """The URL of the image. Can be a data URI like 'data:image/png;base64,...'."""
        detail: Optional[str] = None
        """The detail level: 'low', 'high', or 'auto'."""

    type: str = "image_url"
    image_url: ImageURL


class AudioURLPart(ContentPart):
    """Audio URL content part.

    Attributes:
        audio_url: The audio URL configuration.
    """

    class AudioURL(BaseModel):
        """Audio URL configuration."""

        url: str
        """The URL of the audio. Can be a data URI like 'data:audio/mp3;base64,...'."""

    type: str = "audio_url"
    audio_url: AudioURL


class ToolCall(BaseModel, MergeableMixin):
    """A tool call requested by the assistant.

    Attributes:
        id: Unique identifier for the tool call.
        function: The function to call.

    Example:
        >>> call = ToolCall(
        ...     id="call_123",
        ...     function=ToolCall.FunctionBody(name="add", arguments='{"a": 1, "b": 2}'),
        ... )
    """

    class FunctionBody(BaseModel):
        """Function call details."""

        name: str
        """The name of the tool to call."""
        arguments: str
        """The arguments as a JSON string."""

    type: Literal["function"] = "function"
    id: str
    function: FunctionBody

    def merge_in_place(self, other: Any) -> bool:
        """Merge a ToolCallPart into this ToolCall."""
        if not isinstance(other, ToolCallPart):
            return False
        if other.arguments_part:
            self.function.arguments += other.arguments_part
        return True


class ToolCallPart(BaseModel, MergeableMixin):
    """A partial tool call during streaming.

    This represents a chunk of a tool call that is being streamed.

    Attributes:
        arguments_part: A chunk of the arguments JSON.
    """

    arguments_part: Optional[str] = None

    def merge_in_place(self, other: Any) -> bool:
        """Merge another ToolCallPart into this one."""
        if not isinstance(other, ToolCallPart):
            return False
        if other.arguments_part:
            if self.arguments_part is None:
                self.arguments_part = other.arguments_part
            else:
                self.arguments_part += other.arguments_part
        return True


class Message(BaseModel):
    """A message in a conversation.

    Attributes:
        role: The role of the message sender.
        content: The content parts of the message.
        tool_calls: Tool calls requested by the assistant (only for assistant role).
        tool_call_id: The ID of the tool call being responded to (only for tool role).
        name: Optional name for the sender.

    Example:
        >>> msg = Message(role="user", content="Hello!")
        >>> print(msg.extract_text())
        Hello!
    """

    role: Role
    content: list[ContentPart]
    tool_calls: Optional[list[ToolCall]] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None

    @field_validator("content", mode="before")
    @classmethod
    def _coerce_content(cls, value: Any) -> Any:
        """Coerce string content to TextPart."""
        if isinstance(value, str):
            return [TextPart(text=value)]
        return value

    def __init__(
        self,
        *,
        role: Role,
        content: Union[list[ContentPart], ContentPart, str],
        tool_calls: Optional[list[ToolCall]] = None,
        tool_call_id: Optional[str] = None,
        name: Optional[str] = None,
    ) -> None:
        """Initialize a message.

        Args:
            role: The role of the message sender.
            content: The content, can be a string, single ContentPart, or list.
            tool_calls: Tool calls for assistant messages.
            tool_call_id: ID of the tool call being responded to.
            name: Optional name for the sender.
        """
        if isinstance(content, str):
            content = [TextPart(text=content)]
        elif isinstance(content, ContentPart):
            content = [content]

        super().__init__(
            role=role,
            content=content,
            tool_calls=tool_calls,
            tool_call_id=tool_call_id,
            name=name,
        )

    def extract_text(self, sep: str = "") -> str:
        """Extract all text from the message content.

        Args:
            sep: Separator to use between text parts.

        Returns:
            Concatenated text from all TextPart instances.
        """
        return sep.join(part.text for part in self.content if isinstance(part, TextPart))

    def has_tool_calls(self) -> bool:
        """Check if this message contains tool calls.

        Returns:
            True if the message has tool calls.
        """
        return self.tool_calls is not None and len(self.tool_calls) > 0
